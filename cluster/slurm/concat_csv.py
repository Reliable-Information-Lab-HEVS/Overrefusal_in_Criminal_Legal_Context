#!/usr/bin/env python3
"""Safely concatenate several run.py output CSVs into one file.

Plain `cat`/`tail` corrupts these files: LLM response columns routinely
contain embedded newlines and commas inside quoted fields, which naive
line-based concatenation splits apart. This reads/writes through Python's
csv module instead, so quoting is handled correctly, and adds a `condition`
column (alias of `prefix`) because the already-published
results/english/mcnemar_analysis.py reads `row["condition"]` literally --
that column name predates the current pipeline's `prefix` column and the
script is intentionally left untouched (its numbers are already in the
paper).

Usage:
  python3 concat_csv.py OUT.csv IN1.csv IN2.csv ... [--add-condition]
"""
import argparse
import csv
import sys

csv.field_size_limit(10**8)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("inputs", nargs="+")
    parser.add_argument(
        "--add-condition", action="store_true",
        help="Duplicate the 'prefix' column as 'condition' (English arm only).",
    )
    args = parser.parse_args()

    fieldnames = None
    rows = []
    for path in args.inputs:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if fieldnames is None:
                fieldnames = list(reader.fieldnames)
            elif list(reader.fieldnames) != fieldnames:
                sys.exit(
                    f"Column mismatch: {path} has {reader.fieldnames}, "
                    f"expected {fieldnames}"
                )
            rows.extend(reader)

    if fieldnames is None:
        sys.exit("No input files given.")

    if args.add_condition:
        if "prefix" not in fieldnames:
            sys.exit("--add-condition requires a 'prefix' column in the inputs.")
        fieldnames = fieldnames + ["condition"]
        for r in rows:
            r["condition"] = r["prefix"]

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {args.output} ({len(rows)} rows from {len(args.inputs)} files)")


if __name__ == "__main__":
    main()
