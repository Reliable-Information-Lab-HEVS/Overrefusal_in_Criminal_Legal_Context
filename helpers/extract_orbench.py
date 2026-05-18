#!/usr/bin/env python3
"""Extract OR-Bench prompts by category into a BGer-shaped CSV."""
import csv, sys
from datasets import load_dataset

CATEGORY = sys.argv[1] if len(sys.argv) > 1 else "illegal"
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else "data/orbench_illegal.csv"
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 25

BGER_COLUMNS = [
    "prompt_id", "or_category", "bger_source", "bger_url",
    "task_fr", "task_hard_fr", "task_de", "task_hard_de",
    "task_it", "task_hard_it", "task_en", "task_hard_en",
    "orginal_language",
    "text_fr", "text_de", "text_it", "text_en",
]

print(f"Loading OR-Bench, filtering category = '{CATEGORY}'...")
ds = load_dataset("bench-llm/or-bench", "or-bench-80k", split="train")

# Show what categories actually exist (run once to verify)
seen = sorted(set((x.get("category") or "").strip() for x in ds))
print("Categories present:", seen)

rows = []
for item in ds:
    cat = (item.get("category") or "").strip().lower()
    if cat != CATEGORY.lower():
        continue
    prompt = (item.get("prompt") or "").strip()
    if len(prompt) < 20:
        continue
    rows.append(prompt)
    if len(rows) >= LIMIT:
        break

print(f"Collected {len(rows)} prompts for category '{CATEGORY}'")

with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=BGER_COLUMNS)
    writer.writeheader()
    for i, prompt in enumerate(rows, 1):
        row = {c: "" for c in BGER_COLUMNS}
        row["prompt_id"] = f"orbench_{CATEGORY}_{i:03d}"
        row["or_category"] = CATEGORY
        row["bger_source"] = "OR-Bench-80k"
        row["orginal_language"] = "en"
        row["text_en"] = prompt
        writer.writerow(row)

print(f"Wrote {OUTPUT}")
