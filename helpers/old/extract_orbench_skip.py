#!/usr/bin/env python3
"""Extract OR-Bench prompts, skipping the first SKIP rows."""
import csv, sys
from datasets import load_dataset

CATEGORY = sys.argv[1]
OUTPUT   = sys.argv[2]
LIMIT    = int(sys.argv[3])
SKIP     = int(sys.argv[4]) if len(sys.argv) > 4 else 0

BGER_COLUMNS = ["prompt_id","or_category","bger_source","bger_url",
    "task_fr","task_hard_fr","task_de","task_hard_de","task_it","task_hard_it",
    "task_en","task_hard_en","orginal_language","text_fr","text_de","text_it","text_en"]

ds = load_dataset("bench-llm/or-bench", "or-bench-80k", split="train")

collected = []
for item in ds:
    if (item.get("category") or "").strip().lower() != CATEGORY.lower():
        continue
    p = (item.get("prompt") or "").strip()
    if len(p) < 20:
        continue
    collected.append(p)

chosen = collected[SKIP:SKIP+LIMIT]
print(f"Category '{CATEGORY}': {len(collected)} total, took rows {SKIP+1}-{SKIP+len(chosen)}")

with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=BGER_COLUMNS)
    w.writeheader()
    for i, prompt in enumerate(chosen, SKIP+1):
        row = {c: "" for c in BGER_COLUMNS}
        row["prompt_id"] = f"orbench_{CATEGORY}_{i:04d}"
        row["or_category"] = CATEGORY
        row["bger_source"] = "OR-Bench-80k"
        row["orginal_language"] = "en"
        row["text_en"] = prompt
        w.writerow(row)
print(f"Wrote {OUTPUT}")
