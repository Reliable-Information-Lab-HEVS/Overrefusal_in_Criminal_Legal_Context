"""Offline regression smoke test for the over-refusal artifact.

Runs fully offline (no model server, no API keys) and asserts the behaviors
that the refactor must NOT change:

  * the exact set of CSV columns produced by a run,
  * the "[ERROR] ..." backend-error contract (returned, never raised),
  * the keyword refusal detector (opening-window + EN fallback),
  * prompt loading for the task01 / all task modes.

Usage:
    python tests/smoke_test.py

Exits 0 if every check passes, 1 otherwise. Safe to run on every commit.
"""

import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from over_refusal.detector import RefusalDetector
from over_refusal.evaluation import EvaluationRunner
from over_refusal.prompts import TASK_REGISTRY, get_all_prompts


# The exact columns every result row must carry (the saved CSV header).
EXPECTED_COLUMNS = [
    "prompt_id", "domain", "category", "task_variant", "lang",
    "model", "backend", "prompt", "response_preview", "response_full",
    "is_refused", "is_error",
]

SAMPLE_CSV = str(PROJECT_ROOT / "data" / "sample_TF.csv")

_failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        _failures.append(name)


def test_detector():
    print("detector:")
    d = RefusalDetector()
    # Opening refusals in each language -> True
    check("EN refusal", d.is_refusal("I'm sorry, but I can't help with that.", "en"))
    check("FR refusal", d.is_refusal("Je suis désolé, je ne peux pas vous aider.", "fr"))
    check("DE refusal", d.is_refusal("Als KI-Modell kann ich Ihnen keine Anleitung geben.", "de"))
    # Plain compliant answer -> False
    check("compliant answer", not d.is_refusal("Sure! Here is the summary of the case.", "en"))
    # Empty -> False
    check("empty response", not d.is_refusal("", "en"))
    # English fallback even when lang is FR
    check("EN fallback under FR", d.is_refusal("I cannot assist with this request.", "fr"))


def test_prompts_loading():
    print("prompts:")
    single = get_all_prompts(csv_path=SAMPLE_CSV, limit=2, task_mode="task01")
    check("task01 loads rows", len(single) > 0)
    if single:
        entry = next(iter(single.values()))
        check("entry has task_variant=task01", entry.get("task_variant") == "task01")
        check("entry has 'en' text", "en" in entry)
    allmode = get_all_prompts(csv_path=SAMPLE_CSV, limit=2, task_mode="all")
    check("all-mode emits a __<task> id for every registered task",
          all(any(k.endswith(f"__{t}") for k in allmode) for t in TASK_REGISTRY))


def test_run_columns_and_error_contract():
    print("end-to-end (offline, ollama down -> [ERROR]):")
    runner = EvaluationRunner()
    results = runner.run(
        ollama_only=True,
        # Use a model name GUARANTEED to be absent so the "[ERROR]" contract is
        # exercised whether the Ollama server is off (connection refused) or on
        # (unknown model -> 404). A real installed model would actually answer,
        # is_error would be False, and this check would fail on a healthy machine.
        ollama_models=["__smoke_test_absent_model__"],
        languages=["en"],
        prompts_file=SAMPLE_CSV,
        limit=1,
        task_mode="task01",
    )
    check("produced at least one result", len(results) > 0)
    if results:
        row = results[0]
        check("columns match exactly", list(row.keys()) == EXPECTED_COLUMNS,
              f"got {list(row.keys())}")
        check("backend error returns [ERROR] string",
              row["response_full"].startswith("[ERROR]"))
        check("is_error flag set on error", row["is_error"] is True)


def main():
    print("\n=== OVER-REFUSAL SMOKE TEST (offline) ===\n")
    for fn in (test_detector, test_prompts_loading,
               test_run_columns_and_error_contract):
        try:
            fn()
        except Exception:
            print(f"  [FAIL] {fn.__name__} raised:")
            traceback.print_exc()
            _failures.append(fn.__name__)
        print()

    if _failures:
        print(f"RESULT: FAIL ({len(_failures)} check(s) failed: {_failures})")
        sys.exit(1)
    print("RESULT: PASS (all checks green)")


if __name__ == "__main__":
    main()
