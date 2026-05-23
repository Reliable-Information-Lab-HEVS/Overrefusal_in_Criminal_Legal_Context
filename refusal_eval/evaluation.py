"""Run the over-refusal evaluation.

Pipeline for one (case, language, model):
  1. Build the prompt = task prefix (optional) + case text.
  2. Send it to the model, served locally by Ollama.
  3. Flag a refusal with the keyword detector.
  4. Append a row to the results CSV.

Every model runs locally (Ollama). There is no remote API and no LLM-as-judge:
refusal is decided by the keyword detector only.
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from refusal_eval import reporting, storage
from refusal_eval.clients import OllamaClient
from refusal_eval.config import (
    DEFAULT_LANGUAGES,
    DEFAULT_OLLAMA_MODELS,
    RESULTS_DIR,
    SUPPORTED_LANGUAGES,
)
from refusal_eval.detector import RefusalDetector
from refusal_eval.prompts import load_prompts
from refusal_eval.tasks import NO_TASK, available_tasks, build_prompt, load_task


def run(
    data_file: str,
    task: str = NO_TASK,
    languages: Optional[List[str]] = None,
    models: Optional[List[str]] = None,
    categories: Optional[List[str]] = None,
    prompt_ids: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> List[Dict]:
    languages = languages or DEFAULT_LANGUAGES
    models = models or DEFAULT_OLLAMA_MODELS

    invalid = [l for l in languages if l not in SUPPORTED_LANGUAGES]
    if invalid:
        raise ValueError(f"Unsupported language(s): {invalid}. Supported: {SUPPORTED_LANGUAGES}")

    cases = load_prompts(data_file, categories=categories, prompt_ids=prompt_ids, limit=limit)
    if not cases:
        raise ValueError("No cases matched the given filters.")

    task_texts = load_task(task)  # {lang: prefix}
    client = OllamaClient()
    detector = RefusalDetector()

    total = len(cases) * len(languages) * len(models)
    print("\n" + "=" * 60)
    print("  OVER-REFUSAL EVALUATION")
    print(f"  {len(cases)} cases x {len(languages)} languages x "
          f"{len(models)} models = {total} tests")
    print(f"  Task: {task}")
    print("=" * 60 + "\n")

    results: List[Dict] = []
    count = 0
    for case in cases:
        for lang in languages:
            case_text = case.get(f"text_{lang}", "")
            if not case_text:
                print(f"[skip] {case['prompt_id']} has no text_{lang}")
                continue
            prompt = build_prompt(task_texts.get(lang, ""), case_text)

            for model_name in models:
                count += 1
                print(f"[{count}/{total}] {case['prompt_id']} | {lang} | {task} | "
                      f"{model_name}...", end=" ", flush=True)

                response = client.query(prompt, model_name)
                is_error = response.startswith("[ERROR]")
                is_refused = (not is_error) and detector.is_refusal(response, lang)
                print("ERROR" if is_error else ("REFUSED" if is_refused else "OK"))

                results.append({
                    "prompt_id": case["prompt_id"],
                    "or_category": case["category"],
                    "source": case["source"],
                    "task": task,
                    "lang": lang,
                    "model": model_name,
                    "prompt": prompt,
                    "response": response,
                    "is_refused": is_refused,
                    "is_error": is_error,
                })

    return results


def _default_output(data_file: str, task: str) -> str:
    stem = Path(data_file).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(RESULTS_DIR / f"{stem}_{task}_{timestamp}.csv")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Over-refusal evaluation (local Ollama models)")
    parser.add_argument("--data", required=True,
                        help="Path to the data CSV (prompt_id, or_category, ..., text_*)")
    parser.add_argument("--task", default=NO_TASK,
                        choices=available_tasks() + [NO_TASK],
                        help=f"Task prefix to prepend (default: {NO_TASK} = text only)")
    parser.add_argument("--languages", nargs="+", default=DEFAULT_LANGUAGES,
                        choices=SUPPORTED_LANGUAGES,
                        help=f"Languages to test (default: {DEFAULT_LANGUAGES})")
    parser.add_argument("--models", "--ollama-models", nargs="+", dest="models",
                        default=DEFAULT_OLLAMA_MODELS,
                        help="Ollama model tags to test")
    parser.add_argument("--categories", nargs="+", default=None,
                        help="Filter by or_category")
    parser.add_argument("--prompt-ids", nargs="+", default=None,
                        help="Filter by specific prompt_id values")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap the number of cases (after filters)")
    parser.add_argument("--output", default=None,
                        help="Output CSV path (default: results/<data>_<task>_<ts>.csv)")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    results = run(
        data_file=args.data,
        task=args.task,
        languages=args.languages,
        models=args.models,
        categories=args.categories,
        prompt_ids=args.prompt_ids,
        limit=args.limit,
    )

    output_path = args.output or _default_output(args.data, args.task)
    saved = storage.save_csv(results, output_path)
    reporting.print_summary(results)
    print(f"\nDone! Results in: {saved}")


if __name__ == "__main__":
    main()
