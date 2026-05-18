"""Load BGer prompts from CSV.

The CSV has one row per case with columns:
  prompt_id, or_category, bger_source, bger_url,
  task_fr, task_de, task_it, task_en,                 -- "normal" task (summary)
  task_hard_fr, task_hard_de, task_hard_it, task_hard_en,  -- "hard" task (more specific)
  text_fr, text_de, text_it, text_en                   -- case facts in 4 languages

Filtering options:
  - categories: keep only rows whose or_category is in this list
  - prompt_ids: keep only specific prompt_ids
  - limit: cap the number of source rows
  - task_mode: which task column to use (see below)
"""

import csv
from pathlib import Path
from typing import Dict, List, Optional

from over_refusal.config import DEFAULT_PROMPTS_FILE, SUPPORTED_LANGUAGES


# Valid task modes. "all" emits both variants for the same case.
TASK_MODES = ("normal", "hard", "all")


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

    with open(csv_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
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
