"""Load the prompt dataset.

Each data CSV has exactly these columns:

    prompt_id, or_category, source, orginal_language,
    text_fr, text_de, text_en

One row = one case. The case text is provided per language; `orginal_language`
records the language the text was written in (the others are DeepL translations,
see translate.py).
"""

import csv
from pathlib import Path
from typing import Dict, List, Optional

DATA_COLUMNS = [
    "prompt_id",
    "or_category",
    "source",
    "orginal_language",
    "text_fr",
    "text_de",
    "text_en",
]


def load_prompts(
    csv_path: str,
    categories: Optional[List[str]] = None,
    prompt_ids: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> List[Dict]:
    """Load (and optionally filter) rows from a data CSV.

    Returns a list of dicts with keys: prompt_id, category, source,
    original_language, and text_<lang>.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    rows: List[Dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pid = (row.get("prompt_id") or "").strip()
            category = (row.get("or_category") or "").strip()
            if categories and category not in categories:
                continue
            if prompt_ids and pid not in prompt_ids:
                continue

            rows.append({
                "prompt_id": pid,
                "category": category,
                "source": (row.get("source") or "").strip(),
                "original_language": (row.get("orginal_language") or "").strip().lower(),
                "text_fr": (row.get("text_fr") or "").strip(),
                "text_de": (row.get("text_de") or "").strip(),
                "text_en": (row.get("text_en") or "").strip(),
            })
            if limit is not None and len(rows) >= limit:
                break

    return rows
