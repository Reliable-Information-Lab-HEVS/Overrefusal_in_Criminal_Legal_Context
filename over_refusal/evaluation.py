"""Run the over-refusal evaluation.

Pipeline for one prompt:
  1. Build the full prompt (task instruction + case text), with an optional
     authority/jailbreak prefix.
  2. Send it to each local Ollama model.
  3. Detect a refusal with keyword matching (RefusalDetector).
  4. Save the response and a refusal flag to a CSV row.

Refusal detection is keyword-based only, consistent with the paper.
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from over_refusal.clients import OllamaClient
from over_refusal.config import (
    DEFAULT_LANGUAGES,
    DEFAULT_OLLAMA_MODELS,
    DEFAULT_PROMPTS_FILE,
    DEFAULT_RESULTS_DIR,
    SUPPORTED_LANGUAGES,
)
from over_refusal.detector import RefusalDetector
from over_refusal.prefixes import PREFIX_CHOICES, apply_prefix
from over_refusal.prompts import TASK_MODES, get_all_prompts
from over_refusal.reporting import SummaryPrinter
from over_refusal.storage import ResultSaver


# Truncation limits for what we store in the CSV (keep the file readable)
PROMPT_PREVIEW_CHARS = 200
RESPONSE_PREVIEW_CHARS = 500
TERMINAL_PREVIEW_CHARS = 300


class EvaluationRunner:
    """Orchestrate one full evaluation run across prompts, languages and models.

    All models run locally via Ollama. Remote/server LLM backends were removed:
    the project is on-premises only (data residency + confidentiality), so the
    only backend is the local Ollama server.
    """

    def __init__(self, ollama_url: str = None):
        self.detector = RefusalDetector()
        # Backend name -> client instance (local only). ollama_url lets a run
        # target an alternate local Ollama server (e.g. a second instance
        # pinned to a specific GPU via CUDA_VISIBLE_DEVICES) instead of the
        # shared default one.
        self.clients = {
            "ollama": OllamaClient(base_url=ollama_url) if ollama_url else OllamaClient(),
        }

    def build_models(
        self,
        ollama_models: List[str] = None,
    ) -> List[Tuple[str, str]]:
        """Return the list of (backend, model_name) pairs to test."""
        if ollama_models is None:
            ollama_models = DEFAULT_OLLAMA_MODELS
        return [("ollama", model_name) for model_name in ollama_models]

    def run(
        self,
        ollama_models: List[str] = None,
        languages: List[str] = None,
        prompts_file: Optional[str] = None,
        categories: Optional[List[str]] = None,
        prompt_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
        task_mode: str = "normal",
        prefix: str = "none",
        num_ctx: Optional[int] = None,
        incremental_output: Optional[str] = None,
    ) -> List[Dict]:
        """Run the evaluation and return the list of result dicts.

        If ``incremental_output`` is set, each row is also appended to that
        file immediately as it's produced (flushed to disk), so a crash
        partway through a long run doesn't lose everything already
        completed -- a companion to, not a replacement for, the final
        save_csv() call in main().
        """
        saver = ResultSaver() if incremental_output else None

        if languages is None:
            languages = DEFAULT_LANGUAGES

        # Validate language codes early
        invalid = [l for l in languages if l not in SUPPORTED_LANGUAGES]
        if invalid:
            raise ValueError(
                f"Unsupported language(s): {invalid}. Supported: {SUPPORTED_LANGUAGES}"
            )

        # Load prompts (filtered)
        prompts = get_all_prompts(
            csv_path=prompts_file,
            categories=categories,
            prompt_ids=prompt_ids,
            limit=limit,
            task_mode=task_mode,
        )
        if not prompts:
            raise ValueError(
                "No prompts matched the given filters. "
                "Check --categories / --prompt-ids / --limit."
            )

        models = self.build_models(ollama_models=ollama_models)

        results: List[Dict] = []
        total = len(prompts) * len(languages) * len(models)
        count = 0

        # Run banner
        print("\n" + "=" * 60)
        print("  OVER-REFUSAL EVALUATION")
        print(
            f"  {len(prompts)} prompts x {len(languages)} languages x "
            f"{len(models)} models = {total} tests"
        )
        print(f"  Task mode: {task_mode}")
        print(f"  Prefix: {prefix}")
        if categories:
            print(f"  Categories filter: {categories}")
        if prompt_ids:
            print(f"  Prompt IDs filter: {prompt_ids}")
        if limit is not None:
            print(f"  Limit: {limit}")
        print("=" * 60 + "\n")

        # Triple loop: prompt x language x model
        for prompt_id, prompt_data in prompts.items():
            category = prompt_data["category"]
            task_variant = prompt_data.get("task_variant", "normal")
            domain = "BGR/legal" if prompt_id.startswith("bgr") else "general"

            for language in languages:
                # Fall back to English text if the language is missing for this prompt
                prompt_text = prompt_data.get(language) or prompt_data.get("en", "")
                if not prompt_text:
                    print(f"[skip] {prompt_id} has no text for language '{language}'")
                    continue

                # Inject the authority/jailbreak prefix at run time (if any).
                prompt_text = apply_prefix(prompt_text, prefix, language)

                for backend, model_name in models:
                    count += 1
                    label = f"{prompt_id} | {language} | {task_variant} | {model_name}"
                    print(f"[{count}/{total}] {label}...", end=" ", flush=True)

                    # Send the prompt to the model
                    client = self.clients.get(backend)
                    if client is None:
                        response_text = "[ERROR] Unknown backend"
                    else:
                        response_text = client.query(prompt_text, model_name, num_ctx=num_ctx)

                    # Keyword refusal check
                    refused = self.detector.is_refusal(response_text, language)
                    is_error = response_text.startswith("[ERROR]")

                    # Build the preview that we save and print
                    if is_error:
                        response_preview = response_text
                    else:
                        response_preview = response_text[:RESPONSE_PREVIEW_CHARS].replace("\n", " ")

                    row = {
                        "prompt_id": prompt_id,
                        "domain": domain,
                        "category": category,
                        "task_variant": task_variant,
                        "prefix": prefix,
                        "lang": language,
                        "model": model_name,
                        "backend": backend,
                        "prompt": prompt_text[:PROMPT_PREVIEW_CHARS],
                        "response_preview": response_preview,
                        "response_full": response_text,
                        "is_refused": refused,
                        "is_error": is_error,
                    }
                    results.append(row)
                    if saver is not None:
                        saver.append_row(incremental_output, row)

                    # Print status + a short preview to follow the run live
                    if refused:
                        status = "REFUSED"
                    elif is_error:
                        status = "ERROR"
                    else:
                        status = "OK"
                    print(status)
                    print(f"    -> {response_preview[:TERMINAL_PREVIEW_CHARS]}")
                    print()

        return results


def _resolve_output_path(user_output: Optional[str]) -> str:
    """If the user did not give --output, build a timestamped path inside results/."""
    if user_output:
        out_path = Path(user_output)
        # If the user gave a bare filename, drop it inside the results/ folder
        if not out_path.is_absolute() and out_path.parent == Path("."):
            out_path = Path(DEFAULT_RESULTS_DIR) / out_path.name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return str(out_path)

    Path(DEFAULT_RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(Path(DEFAULT_RESULTS_DIR) / f"over_refusal_results_{timestamp}.csv")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Over-Refusal Evaluation")

    # --- Model selection (all models run locally via Ollama) ---
    parser.add_argument("--ollama-models", nargs="+", default=DEFAULT_OLLAMA_MODELS,
                        help="List of Ollama models to test")

    # --- Language selection ---
    parser.add_argument("--languages", nargs="+", default=DEFAULT_LANGUAGES,
                        choices=SUPPORTED_LANGUAGES,
                        help=f"Languages to test. Choices: {SUPPORTED_LANGUAGES}")

    # --- Prompt filtering ---
    parser.add_argument("--prompts-file", type=str, default=DEFAULT_PROMPTS_FILE,
                        help="Path to the prompts CSV")
    parser.add_argument("--categories", nargs="+", default=None,
                        help="Filter by or_category (e.g. sexual violence illegal self-harm)")
    parser.add_argument("--prompt-ids", nargs="+", default=None,
                        help="Filter by specific prompt_id values (e.g. bgr_01 bgr_05)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit total number of prompts (after filters)")

    # --- Task variant ---
    parser.add_argument("--task-mode", choices=list(TASK_MODES), default="normal",
                        help="Which task column to use: normal, hard, or all (both)")

    # --- Prefix condition (injected at run time) ---
    parser.add_argument("--prefix", choices=PREFIX_CHOICES, default="none",
                        help="Authority/jailbreak prefix prepended to every prompt "
                             "(per language). Default: none (baseline).")
    parser.add_argument("--num-ctx", type=int, default=None,
                        help="Explicit Ollama context window (tokens) for this run. "
                             "Default: unset, i.e. Ollama's own default. Recommended "
                             "for long documents to avoid silent truncation.")
    parser.add_argument("--ollama-url", type=str, default=None,
                        help="Alternate Ollama /api/generate URL (e.g. a second "
                             "local instance on another port/GPU). Default: the "
                             "shared server from over_refusal/config.py.")
    parser.add_argument("--incremental-output", type=str, default=None,
                        help="Also append each row to this CSV as it's produced "
                             "(flushed immediately), so a crash partway through a "
                             "long run doesn't lose completed results. The final "
                             "--output file is still written as usual at the end.")

    # --- Shortcut & output ---
    parser.add_argument("--quick", action="store_true",
                        help="Quick test: 3 prompts, English only")
    parser.add_argument("--output", type=str, default=None,
                        help="Output CSV filename (saved under results/ by default)")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    # --quick is a shortcut that overrides limit and languages
    limit = args.limit
    languages = args.languages
    if args.quick:
        limit = 3 if limit is None else min(limit, 3)
        languages = ["en"]
        print("QUICK MODE: 3 prompts, English only\n")

    runner = EvaluationRunner(ollama_url=args.ollama_url)
    saver = ResultSaver()
    printer = SummaryPrinter()

    results = runner.run(
        ollama_models=args.ollama_models,
        languages=languages,
        prompts_file=args.prompts_file,
        categories=args.categories,
        prompt_ids=args.prompt_ids,
        limit=limit,
        task_mode=args.task_mode,
        prefix=args.prefix,
        num_ctx=args.num_ctx,
        incremental_output=args.incremental_output,
    )

    output_path = _resolve_output_path(args.output)
    filename = saver.save_csv(results, output_path)
    printer.print_summary(results)

    print(f"\nDone! Full results in: {filename}")
