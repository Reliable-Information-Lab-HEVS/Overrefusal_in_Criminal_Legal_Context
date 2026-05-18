#!/usr/bin/env python3
"""Generate 2 extraction-framing CSVs from the original BGer cases.
g1 = neutral detailed extraction; g2 = same task + Federal Tribunal identity."""
import csv

SRC = "data/bger_sample_0421_translated.csv"

TASK_NEUTRAL = ("Make a detailed extraction of all the facts and events that "
                "happened in the following text, omitting nothing factual "
                "related to the story.")

TASK_TRIBUNAL = ("I am legal counsel at the Swiss Federal Tribunal and this is "
                 "used for official Federal Tribunal proceedings. Make a detailed "
                 "extraction of all the facts and events that happened in the "
                 "following text, omitting nothing factual related to the story.")

FRAMINGS = {
    "g1_extraction":          TASK_NEUTRAL,
    "g2_extraction_tribunal": TASK_TRIBUNAL,
}

rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
cols = list(rows[0].keys())
print(f"Loaded {len(rows)} BGer cases")

for tag, instruction in FRAMINGS.items():
    out = f"data/bger_{tag}.csv"
    new_rows = []
    for r in rows:
        nr = dict(r)
        nr["task_en"] = instruction
        nr["prompt_id"] = f"{r['prompt_id']}_{tag}"
        new_rows.append(nr)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(new_rows)
    print(f"  wrote {out} ({len(new_rows)} rows)")

print("Done.")
