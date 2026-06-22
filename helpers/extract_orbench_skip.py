#!/usr/bin/env python3
"""Extract OR-Bench prompts by category into a BGer-shaped CSV.

Usage: python extract_orbench_skip.py <category> <output.csv> <limit> <skip>
  - skip: how many matching prompts to skip from the start (default 0)
  - limit: how many prompts to take after skipping
"""
import csv, sys
from datasets import load_dataset

CATEGORY = sys.argv[1] if len(sys.argv) > 1 else "illegal"
OUTPUT   = sys.argv[2] if len(sys.argv) > 2 else "data/orbench_illegal.csv"
LIMIT    = int(sys.argv[3]) if len(sys.argv) > 3 else 25
SKIP     = int(sys.argv[4]) if len(sys.argv) > 4 else 0

BGER_COLUMNS = [
    "prompt_id", "or_category", "bger_source", "bger_url",
    "task_fr", "task_hard_fr", "task_de", "task_hard_de",
    "task_it", "task_hard_it", "task_en", "task_hard_en",
    "orginal_language",
    "text_fr", "text_de", "text_it", "text_en",
]

print(f"Loading OR-Bench, filtering category = '{CATEGORY}', skipping {SKIP}, taking {LIMIT}...")
ds = load_dataset("bench-llm/or-bench", "or-bench-80k", split="train")

rows = []
skipped = 0
for item in ds:
    cat = (item.get("category") or "").strip().lower()
    if cat != CATEGORY.lower():
        continue
    prompt = (item.get("prompt") or "").strip()
    if len(prompt) < 20:
        continue
    if skipped < SKIP:
        skipped += 1
        continue
    rows.append(prompt)
    if len(rows) >= LIMIT:
        break

print(f"Collected {len(rows)} prompts for category '{CATEGORY}' (after skipping {skipped})")

with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=BGER_COLUMNS)
    writer.writeheader()
    for i, prompt in enumerate(rows, 1):
        # Numbering continues from SKIP+1 so IDs don't collide with the first batch
        idx = SKIP + i
        row = {c: "" for c in BGER_COLUMNS}
        row["prompt_id"] = f"orbench_{CATEGORY}_{idx:04d}"
        row["or_category"] = CATEGORY
        row["bger_source"] = "OR-Bench-80k"
        row["orginal_language"] = "en"
        row["text_en"] = prompt
        writer.writerow(row)
print(f"Wrote {OUTPUT}")