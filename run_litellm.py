#!/usr/bin/env python3
"""Run the over-refusal evaluation against a hosted LLM behind a LiteLLM
proxy (e.g. moonshotai/Kimi-K2.6 via the armasuisse gateway), instead of a
local Ollama model.

This is a SEPARATE, standalone script -- not part of the on-premises
pipeline (run.py / over_refusal/). It reuses that pipeline's prompt
loading, prefix injection, and keyword refusal detector so its output CSV
has the exact same schema as run.py's (helpers/refusal_summary.py and
friends work on it unchanged), but the actual model call goes through
litellm_client.LiteLLMClient to a remote gateway, not a local server. See
that module's docstring for why this is kept separate and what NOT to run
it on.

Requires LITELLM_API_KEY in the environment:
    export LITELLM_API_KEY=sk-...
    python3 run_litellm.py --prompts-file data/orbench_violence200.csv --quick

Sanity-check first (3 prompts, English only, matches run.py --quick):
    python3 run_litellm.py --quick

Full example:
    python3 run_litellm.py --prompts-file data/orbench_violence200.csv \
        --languages en --prefix none --model moonshotai/Kimi-K2.6 \
        --output results/litellm/orbench_violence200_none.csv
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from litellm_client import LiteLLMClient
from over_refusal.config import DEFAULT_LANGUAGES, SUPPORTED_LANGUAGES
from over_refusal.detector import RefusalDetector
from over_refusal.prefixes import PREFIX_CHOICES, apply_prefix
from over_refusal.prompts import TASK_MODES, get_all_prompts
from over_refusal.storage import ResultSaver

PROMPT_PREVIEW_CHARS = 200
RESPONSE_PREVIEW_CHARS = 500
TERMINAL_PREVIEW_CHARS = 300
DEFAULT_LITELLM_RESULTS_DIR = "results/litellm"


def run(
    model: str,
    prompts_file: Optional[str] = None,
    languages: List[str] = None,
    categories: Optional[List[str]] = None,
    prompt_ids: Optional[List[str]] = None,
    limit: Optional[int] = None,
    task_mode: str = "normal",
    prefix: str = "none",
    max_tokens: int = 1024,
    incremental_output: Optional[str] = None,
) -> List[dict]:
    client = LiteLLMClient()
    detector = RefusalDetector()
    saver = ResultSaver() if incremental_output else None

    if languages is None:
        languages = DEFAULT_LANGUAGES
    invalid = [l for l in languages if l not in SUPPORTED_LANGUAGES]
    if invalid:
        raise ValueError(f"Unsupported language(s): {invalid}. Supported: {SUPPORTED_LANGUAGES}")

    prompts = get_all_prompts(
        csv_path=prompts_file,
        categories=categories,
        prompt_ids=prompt_ids,
        limit=limit,
        task_mode=task_mode,
    )
    if not prompts:
        raise ValueError("No prompts matched the given filters.")

    results = []
    total = len(prompts) * len(languages)
    count = 0

    print("\n" + "=" * 60)
    print("  OVER-REFUSAL EVALUATION (LiteLLM / hosted model)")
    print(f"  {len(prompts)} prompts x {len(languages)} languages = {total} tests")
    print(f"  Model: {model}")
    print(f"  Task mode: {task_mode}")
    print(f"  Prefix: {prefix}")
    print("=" * 60 + "\n")

    for prompt_id, prompt_data in prompts.items():
        category = prompt_data["category"]
        task_variant = prompt_data.get("task_variant", "normal")
        domain = "BGR/legal" if prompt_id.startswith("bgr") else "general"

        for language in languages:
            prompt_text = prompt_data.get(language) or prompt_data.get("en", "")
            if not prompt_text:
                print(f"[skip] {prompt_id} has no text for language '{language}'")
                continue

            prompt_text = apply_prefix(prompt_text, prefix, language)

            count += 1
            print(f"[{count}/{total}] {prompt_id} | {language} | {task_variant} | {model}...", end=" ", flush=True)

            response_text = client.query(prompt_text, model, max_tokens=max_tokens)

            refused = detector.is_refusal(response_text, language)
            is_error = response_text.startswith("[ERROR]")
            response_preview = (
                response_text if is_error else response_text[:RESPONSE_PREVIEW_CHARS].replace("\n", " ")
            )

            row = {
                "prompt_id": prompt_id,
                "domain": domain,
                "category": category,
                "task_variant": task_variant,
                "prefix": prefix,
                "lang": language,
                "model": model,
                "backend": "litellm",
                "prompt": prompt_text[:PROMPT_PREVIEW_CHARS],
                "response_preview": response_preview,
                "response_full": response_text,
                "is_refused": refused,
                "is_error": is_error,
            }
            results.append(row)
            if saver is not None:
                saver.append_row(incremental_output, row)

            status = "REFUSED" if refused else ("ERROR" if is_error else "OK")
            print(status)
            print(f"    -> {response_preview[:TERMINAL_PREVIEW_CHARS]}")
            print()

    return results


def _resolve_output_path(user_output: Optional[str]) -> str:
    if user_output:
        out_path = Path(user_output)
        if not out_path.is_absolute() and out_path.parent == Path("."):
            out_path = Path(DEFAULT_LITELLM_RESULTS_DIR) / out_path.name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return str(out_path)

    Path(DEFAULT_LITELLM_RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(Path(DEFAULT_LITELLM_RESULTS_DIR) / f"litellm_results_{timestamp}.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Over-Refusal Evaluation (LiteLLM-hosted model)")
    parser.add_argument("--model", type=str, default="moonshotai/Kimi-K2.6",
                         help="Model name as known to the LiteLLM gateway")
    parser.add_argument("--max-tokens", type=int, default=1024,
                         help="Generation budget. Reasoning models need headroom beyond the "
                              "final answer for their reasoning_content trace, or content "
                              "comes back empty -- see litellm_client.py.")
    parser.add_argument("--languages", nargs="+", choices=SUPPORTED_LANGUAGES, default=None)
    parser.add_argument("--prompts-file", type=str, default=None)
    parser.add_argument("--categories", nargs="+", default=None)
    parser.add_argument("--prompt-ids", nargs="+", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--task-mode", choices=TASK_MODES, default="normal")
    parser.add_argument("--prefix", choices=PREFIX_CHOICES, default="none")
    parser.add_argument("--incremental-output", type=str, default=None)
    parser.add_argument("--quick", action="store_true", help="Quick test: 3 prompts, English only")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    limit = args.limit
    languages = args.languages
    if args.quick:
        limit = 3 if limit is None else min(limit, 3)
        languages = ["en"]

    results = run(
        model=args.model,
        prompts_file=args.prompts_file,
        languages=languages,
        categories=args.categories,
        prompt_ids=args.prompt_ids,
        limit=limit,
        task_mode=args.task_mode,
        prefix=args.prefix,
        max_tokens=args.max_tokens,
        incremental_output=args.incremental_output,
    )

    if results:
        output_path = _resolve_output_path(args.output)
        ResultSaver().save_csv(results, output_path)


if __name__ == "__main__":
    main()
