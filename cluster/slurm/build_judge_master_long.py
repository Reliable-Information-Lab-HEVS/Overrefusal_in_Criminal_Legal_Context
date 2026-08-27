#!/usr/bin/env python3
"""Rebuild results/LLM-as-a-judge-final-aggregated-results/judge_master_long.csv
from fresh run_judge.py output.

This file does not come from any script in the repo -- it was hand-exported
from a spreadsheet tool at some point (semicolon line terminator, and the
entire row is quoted as one field only when it contains a literal double
quote, which is exactly what you get from a semicolon-locale CSV export of a
sheet whose single populated column already held comma-joined text). Both
results/english/mcnemar_analysis.py and results/french_german/
mcnemar_analysis.py hard-depend on this exact file and parse it with a
hand-rolled reader tied to that exact byte format -- they are already
published with the paper and are intentionally left untouched here, so this
script reproduces the format exactly rather than switching to a normal CSV.

Format per row, reverse-engineered and verified byte-for-byte (99.8% exact,
remainder is a handful of legacy rows missing a harmless trailing ';' that
the existing reader's rstrip(';') tolerates anyway) against the real
committed file. It's CSV nested inside CSV -- the signature of a spreadsheet
tool exporting a sheet whose one populated column already held pre-built,
comma-joined row strings, using a semicolon-locale "CSV" export:

  level1 = one RFC4180 CSV row of the 9 fields below (only judge_reason
           ever needs quoting -- it's the only field that can contain a
           comma or a literal '"')
  if '"' in level1:  write  '"' + level1.replace('"', '""') + '";'
  else:               write  level1 + ';'

  fields = [prompt_id__prefix, category, task_variant, lang, model,
            is_refused_keyword, judge, judge_label, judge_reason]

Input: one or more CSVs shaped like run_judge.py's own --out format
(columns: prompt_id, category, lang, model, prefix, is_refused_keyword,
judge_saw_request, judge, judge_label, judge_reason). task_variant isn't in
that format; it's hardcoded to "normal" here, matching every row of the
existing committed file (this repo's OR-Bench runs never use
--task-mode hard for the arms that feed this file).

Usage:
  python3 build_judge_master_long.py OUT.csv IN1.csv IN2.csv ...
"""
import argparse
import csv
import io
import sys

csv.field_size_limit(10**8)

FIELDS_OUT = [
    "prompt_id", "category", "task_variant", "lang", "model",
    "is_refused_keyword", "judge", "judge_label", "judge_reason",
]


def encode_row(fields) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(fields)
    level1 = buf.getvalue()
    if '"' in level1:
        return '"' + level1.replace('"', '""') + '";'
    return level1 + ";"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("inputs", nargs="+")
    args = parser.parse_args()

    n = 0
    with open(args.output, "w", encoding="utf-8", newline="") as out:
        out.write(",".join(FIELDS_OUT) + ";\n")
        for path in args.inputs:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                missing = {"prompt_id", "category", "lang", "model", "prefix",
                           "is_refused_keyword", "judge", "judge_label",
                           "judge_reason"} - set(reader.fieldnames or [])
                if missing:
                    sys.exit(f"{path}: missing columns {missing}")
                for row in reader:
                    fields = [
                        f"{row['prompt_id']}__{row['prefix']}",
                        row["category"],
                        "normal",
                        row["lang"],
                        row["model"],
                        row["is_refused_keyword"],
                        row["judge"],
                        row["judge_label"],
                        row["judge_reason"],
                    ]
                    out.write(encode_row(fields) + "\n")
                    n += 1

    print(f"Wrote {args.output} ({n} rows from {len(args.inputs)} files)")


if __name__ == "__main__":
    main()
