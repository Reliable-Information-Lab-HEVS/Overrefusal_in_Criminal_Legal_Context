"""Write evaluation results to a CSV file."""

import csv
from pathlib import Path
from typing import Dict, List

RESULT_COLUMNS = [
    "prompt_id",
    "or_category",
    "source",
    "task",
    "lang",
    "model",
    "prompt",
    "response",
    "is_refused",
    "is_error",
]


def save_csv(results: List[Dict], path: str) -> str:
    if not results:
        raise ValueError("No results to save")
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    return str(out_path)
