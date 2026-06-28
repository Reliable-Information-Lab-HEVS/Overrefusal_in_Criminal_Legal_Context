"""Load evaluation scenarios from a CSV (the input contract).

All input sources — the OR-Bench category files, the BGer/real-text samples and
the Federal Tribunal's own cases — share ONE canonical header:

  prompt_id, or_category, bger_source, bger_url,
  task_fr, task_hard_fr, task_de, task_hard_de, task_it, task_hard_it,
  task_en, task_hard_en, orginal_language,
  text_fr, text_de, text_it, text_en

Column contract (see data/INPUT_FORMAT.md for the full table):

  REQUIRED   prompt_id           unique id for the case
             or_category         topic label used for grouping/filtering
             text_<lang>         the case text in at least ONE supported language

  OPTIONAL   text_<other langs>  additional languages
             task_<lang>         instruction prepended to the text ("normal" task)
             task_hard_<lang>    legacy "hard" task variant
             bger_source/_url    provenance metadata
             orginal_language    informational only

The loader is tolerant: missing optional columns are fine (the Tribunal will
often supply only one or two languages and no task_hard_*), and a row missing a
REQUIRED field is skipped with a warning rather than producing a malformed
prompt. Existing full-schema CSVs load exactly as before.

Filtering options:
  - categories: keep only rows whose or_category is in this list
  - prompt_ids: keep only specific prompt_ids
  - limit: cap the number of source rows
  - task_mode: which task column to use (see below)
"""

import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional

from over_refusal.config import DEFAULT_PROMPTS_FILE, SUPPORTED_LANGUAGES


# Valid task modes. "all" emits both variants for the same case.
TASK_MODES = ("normal", "hard", "all")

# --- Canonical column contract -------------------------------------------------
# A row needs prompt_id, or_category and at least one text_<lang> to be usable;
# everything else is optional and tolerated when absent.
REQUIRED_COLUMNS = ("prompt_id", "or_category")
TEXT_COLUMNS = tuple(f"text_{lang}" for lang in SUPPORTED_LANGUAGES)
OPTIONAL_COLUMNS = (
    tuple(f"task_{lang}" for lang in SUPPORTED_LANGUAGES)
    + tuple(f"task_hard_{lang}" for lang in SUPPORTED_LANGUAGES)
    + ("bger_source", "bger_url", "orginal_language")
)


def _build_prompt_text(task: str, text: str) -> str:
    """Glue a task instruction and the case text into one prompt string."""
    task = (task or "").strip()
    text = (text or "").strip()
    if not text:
        return task
    if not task:
        return text
    return f"{task}\n\n{text}"


def _make_entry(row: dict, task_col_prefix: str) -> dict:
    """Turn one CSV row into a prompt entry dict, for a given task column.

    task_col_prefix is either "task" (normal) or "task_hard".
    """
    entry = {
        "category": row.get("or_category", "").strip(),
        "source": row.get("bger_source", "").strip(),
        "url": row.get("bger_url", "").strip(),
        "task_variant": "normal" if task_col_prefix == "task" else "hard",
    }
    for lang in SUPPORTED_LANGUAGES:
        task = row.get(f"{task_col_prefix}_{lang}", "")
        text = row.get(f"text_{lang}", "")
        entry[lang] = _build_prompt_text(task, text)
    return entry


def _row_problem(row: dict) -> Optional[str]:
    """Return a human-readable reason if a REQUIRED field is missing, else None.

    Required = a non-empty prompt_id, a non-empty or_category, and case text in
    at least one supported language. Optional columns (other languages,
    task_hard_*, provenance) are never required here.
    """
    if not (row.get("prompt_id") or "").strip():
        return "missing prompt_id"
    pid = row["prompt_id"].strip()
    if not (row.get("or_category") or "").strip():
        return f"{pid}: missing or_category"
    if not any((row.get(col) or "").strip() for col in TEXT_COLUMNS):
        langs = "/".join(SUPPORTED_LANGUAGES)
        return f"{pid}: no text in any language (need one of text_{{{langs}}})"
    return None


def load_prompts_from_csv(
    csv_path: str = None,
    categories: Optional[List[str]] = None,
    prompt_ids: Optional[List[str]] = None,
    limit: Optional[int] = None,
    task_mode: str = "normal",
) -> Dict[str, Dict]:
    """Load prompts from CSV with optional filtering.

    task_mode:
      - "normal": use task_XX columns
      - "hard":   use task_hard_XX columns
      - "all":    emit both variants; IDs become bgr_01__normal / bgr_01__hard

    Rows missing a required field (prompt_id, or_category, or any text) are
    skipped with a warning on stderr; missing optional columns are tolerated.
    """
    if task_mode not in TASK_MODES:
        raise ValueError(f"task_mode must be one of {TASK_MODES}, got '{task_mode}'")

    if csv_path is None:
        csv_path = DEFAULT_PROMPTS_FILE

    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Prompts file not found: {csv_path}")

    prompts: Dict[str, Dict] = {}
    rows_kept = 0
    skipped = 0

    with open(csv_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)

        # Light header check: warn (don't crash) if a required column is absent.
        header = reader.fieldnames or []
        missing_required = [c for c in REQUIRED_COLUMNS if c not in header]
        if not any(c in header for c in TEXT_COLUMNS):
            missing_required.append("text_<lang> (need at least one)")
        if missing_required:
            print(
                f"[prompts] warning: {csv_path.name} is missing required column(s): "
                f"{', '.join(missing_required)}",
                file=sys.stderr,
            )

        for line_no, row in enumerate(reader, start=2):  # line 1 is the header
            problem = _row_problem(row)
            if problem:
                print(
                    f"[prompts] skipping row {line_no} ({csv_path.name}): {problem}",
                    file=sys.stderr,
                )
                skipped += 1
                continue

            pid = row["prompt_id"].strip()
            category = row.get("or_category", "").strip()

            # Apply filters
            if categories and category not in categories:
                continue
            if prompt_ids and pid not in prompt_ids:
                continue

            # Build entries depending on task_mode
            if task_mode == "normal":
                prompts[pid] = _make_entry(row, "task")
            elif task_mode == "hard":
                prompts[pid] = _make_entry(row, "task_hard")
            else:  # "all"
                prompts[f"{pid}__normal"] = _make_entry(row, "task")
                prompts[f"{pid}__hard"] = _make_entry(row, "task_hard")

            rows_kept += 1
            if limit is not None and rows_kept >= limit:
                break

    if skipped:
        print(
            f"[prompts] {csv_path.name}: kept {rows_kept} row(s), skipped {skipped}",
            file=sys.stderr,
        )

    return prompts


# Backward-compatible alias used by EvaluationRunner
def get_all_prompts(
    csv_path: str = None,
    categories: Optional[List[str]] = None,
    prompt_ids: Optional[List[str]] = None,
    limit: Optional[int] = None,
    task_mode: str = "normal",
) -> Dict[str, Dict]:
    return load_prompts_from_csv(
        csv_path=csv_path,
        categories=categories,
        prompt_ids=prompt_ids,
        limit=limit,
        task_mode=task_mode,
    )
