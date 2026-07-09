#!/usr/bin/env python3
"""Aggregate rebuttal-run result CSVs into a model x condition summary table.

Usage:
    python aggregate_rebuttal.py results/rebuttal_*.csv
    python aggregate_rebuttal.py            # defaults to results/rebuttal_*.csv

Reads every result CSV given (files produced by run.py, which carry a
``condition`` column), counts refusals per (model, condition), and writes the
summary to results/rebuttal_summary.csv. Rows with is_error=True are counted
separately and excluded from the refusal count.
"""

import csv
import glob
import sys
from collections import defaultdict
from pathlib import Path

# Priority order used for the runs; unknown conditions are appended at the end.
CONDITION_ORDER = [
    "none", "supreme-court", "supreme-court-p1", "lawyer", "lawyer-p1",
    "neutral",
]

OUT_FILE = Path("results") / "rebuttal_summary.csv"


def main() -> None:
    patterns = sys.argv[1:] or ["results/rebuttal_*.csv"]
    files = sorted({f for p in patterns for f in glob.glob(p)})
    files = [f for f in files if Path(f).name != OUT_FILE.name]
    if not files:
        sys.exit(f"No result CSVs matched {patterns}")

    # (model, condition) -> counters
    stats = defaultdict(lambda: {"n": 0, "refused": 0, "errors": 0})
    for path in files:
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = (row["model"], row.get("condition", ""))
                s = stats[key]
                if row.get("is_error") == "True":
                    s["errors"] += 1
                    continue
                s["n"] += 1
                if row.get("is_refused") == "True":
                    s["refused"] += 1

    models = sorted({m for m, _ in stats})
    conditions = [c for c in CONDITION_ORDER if any(k[1] == c for k in stats)]
    conditions += sorted({c for _, c in stats} - set(conditions))

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["model", "condition", "n", "refused", "errors"])
        for model in models:
            for cond in conditions:
                if (model, cond) in stats:
                    s = stats[(model, cond)]
                    writer.writerow([model, cond, s["n"], s["refused"], s["errors"]])

    # Pivot table on stdout: one row per model, one column per condition.
    width = max((len(c) for c in conditions), default=10) + 2
    print(f"\nRefusal counts (refused/n) from {len(files)} file(s):\n")
    print(" " * 62 + "".join(c.rjust(width) for c in conditions))
    for model in models:
        cells = []
        for cond in conditions:
            s = stats.get((model, cond))
            cells.append(("-" if s is None else f"{s['refused']}/{s['n']}").rjust(width))
        print(model.ljust(62) + "".join(cells))
    print(f"\nSummary written to: {OUT_FILE}")


if __name__ == "__main__":
    main()
