#!/usr/bin/env python3
"""Per-model refusal summary table for one run.py output CSV.

Reusable across experiments (any CSV with the standard run.py columns:
model, is_refused, is_error, ...). Groups by model and prints/writes
n / refused / errors / rate, plus an overall total row.

Usage:
    python helpers/refusal_summary.py results/some_run.csv
    python helpers/refusal_summary.py results/some_run.csv --output summary.txt
    python helpers/refusal_summary.py results/some_run.csv --label "kindergarten"
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import List


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def build_table(csv_path: str, label: str = None) -> str:
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    if not rows:
        return f"{csv_path}: no rows"

    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)

    lines: List[str] = []
    title = label or Path(csv_path).name
    lines.append(f"=== {title} ===")
    lines.append(f"{'model':60s} {'n':>5} {'refused':>8} {'errors':>7} {'rate':>7}")

    total_n = total_refused = total_errors = 0
    for model in sorted(by_model.keys()):
        rs = by_model[model]
        n = len(rs)
        refused = sum(1 for r in rs if _truthy(r.get("is_refused", "")))
        errors = sum(1 for r in rs if _truthy(r.get("is_error", "")))
        rate = refused / n * 100 if n else 0.0
        lines.append(f"{model:60s} {n:5d} {refused:8d} {errors:7d} {rate:6.1f}%")
        total_n += n
        total_refused += refused
        total_errors += errors

    total_rate = total_refused / total_n * 100 if total_n else 0.0
    lines.append(f"{'TOTAL':60s} {total_n:5d} {total_refused:8d} {total_errors:7d} {total_rate:6.1f}%")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-model refusal summary for a run.py output CSV")
    parser.add_argument("csv_paths", nargs="+", help="One or more results CSV files")
    parser.add_argument("--label", default=None,
                         help="Title for the table (only valid with a single csv_path; "
                              "defaults to the filename)")
    parser.add_argument("--output", default=None, help="Write the table to this file instead of/besides stdout")
    args = parser.parse_args()

    if args.label and len(args.csv_paths) > 1:
        parser.error("--label can only be used with a single csv_path")

    blocks = [build_table(p, label=args.label) for p in args.csv_paths]
    text = "\n\n".join(blocks)

    print(text)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"\nWritten to {args.output}")


if __name__ == "__main__":
    main()
