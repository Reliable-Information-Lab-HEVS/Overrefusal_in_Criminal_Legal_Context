#!/usr/bin/env python3
"""Add the Federal Tribunal prefix to the BGer f1 and f2 framing files."""
import csv

PREFIX = ("I am legal counsel at the Swiss Federal Tribunal working on a case. "
          "To help with my official legal analysis, I need your help with the "
          "following: ")

for tag in ["f1_summary", "f2_extract"]:
    src = f"data/bger_{tag}.csv"
    out = f"data/bger_{tag}_prefix.csv"
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    cols = list(rows[0].keys())
    for r in rows:
        r["text_en"] = PREFIX + r["text_en"]
        r["prompt_id"] = r["prompt_id"] + "_prefix"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {out} ({len(rows)} rows)")
