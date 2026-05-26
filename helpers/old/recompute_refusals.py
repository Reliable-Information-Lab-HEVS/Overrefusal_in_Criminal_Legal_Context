"""Recompute the `is_refused` column on existing result CSVs.

The generation step (model responses) is expensive; the keyword refusal check
is cheap and lives entirely in `refusal_keywords.json` + `RefusalDetector`.
When the keyword list is updated, this script re-applies the *current*
detector to already-produced result files in place, so the 3000 model calls
never have to be repeated.

It uses the exact production detector (over_refusal.detector.RefusalDetector),
so the recomputed flags match what a fresh run would now produce.

Usage:
    python recompute_refusals.py results/llama8b_harmful_frdeit.csv ...
    python recompute_refusals.py results/llama8b_*.csv        # shell-expanded
    python recompute_refusals.py                              # all results/llama8b_*_frdeit.csv
"""

from __future__ import annotations

import csv
import glob
import sys
from collections import defaultdict
from pathlib import Path

from over_refusal.detector import RefusalDetector

PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_ROOT / "results"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)  # atomic on the same filesystem


def recompute_file(path: Path, detector: RefusalDetector) -> None:
    if not path.exists():
        print(f"[skip] {path.name}: not found")
        return

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if "is_refused" not in fieldnames:
        print(f"[skip] {path.name}: no is_refused column")
        return

    # Prefer the full response if the run stored it; fall back to the preview
    # for older files that only kept the 500-char preview.
    text_col = "response_full" if "response_full" in fieldnames else "response_preview"
    if text_col == "response_preview":
        print(f"  [warn] {path.name}: no 'response_full', detecting on truncated preview")

    # before/after refusal counts per language
    before = defaultdict(int)
    after = defaultdict(int)
    flipped = 0

    for row in rows:
        lang = row.get("lang", "en")
        was = row.get("is_refused") == "True"
        # Errors are not refusals; mirror the runner which sets is_refused on the response.
        if row.get("is_error") == "True":
            now = was  # leave error rows untouched
        else:
            now = detector.is_refusal(row.get(text_col, ""), lang)
        before[lang] += int(was)
        after[lang] += int(now)
        if now != was:
            flipped += 1
        row["is_refused"] = str(now)

    _write_csv(path, fieldnames, rows)

    langs = sorted(set(list(before) + list(after)))
    parts = " ".join(f"{l}:{before[l]}->{after[l]}" for l in langs)
    print(f"[{path.name}] {flipped} flag(s) changed | refusals {parts}")


def main() -> int:
    args = sys.argv[1:]
    if args:
        paths = [Path(p) for p in args]
    else:
        paths = [Path(p) for p in sorted(glob.glob(str(RESULTS_DIR / "llama8b_*_frdeit.csv")))]

    if not paths:
        print("No result files found. Pass paths or place files in results/.")
        return 1

    detector = RefusalDetector()  # loads the current refusal_keywords.json
    for path in paths:
        recompute_file(path, detector)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
