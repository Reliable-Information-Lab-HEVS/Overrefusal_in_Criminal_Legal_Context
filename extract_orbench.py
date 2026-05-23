#!/usr/bin/env python3
"""Extract OR-Bench prompts of one category into the clean data CSV format.

Output columns match refusal_eval/prompts.py:
    prompt_id, or_category, source, orginal_language, text_fr, text_de, text_en

Only `text_en` is filled (OR-Bench is English); run `refusal_eval.translate`
afterwards to populate `text_fr` / `text_de` via DeepL.

    python extract_orbench.py illegal data/orbench_illegal.csv 200
"""

import csv
import sys

from datasets import load_dataset

CATEGORY = sys.argv[1] if len(sys.argv) > 1 else "illegal"
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else f"data/orbench_{CATEGORY}.csv"
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 200
MIN_CHARS = 20

COLUMNS = ["prompt_id", "or_category", "source", "orginal_language",
           "text_fr", "text_de", "text_en"]

print(f"Loading OR-Bench, filtering category = '{CATEGORY}'...")
ds = load_dataset("bench-llm/or-bench", "or-bench-80k", split="train")

prompts = []
for item in ds:
    if (item.get("category") or "").strip().lower() != CATEGORY.lower():
        continue
    text = (item.get("prompt") or "").strip()
    if len(text) < MIN_CHARS:
        continue
    prompts.append(text)
    if len(prompts) >= LIMIT:
        break

print(f"Collected {len(prompts)} prompts for '{CATEGORY}'")
with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=COLUMNS)
    writer.writeheader()
    for i, text in enumerate(prompts, 1):
        writer.writerow({
            "prompt_id": f"orbench_{CATEGORY}_{i:04d}",
            "or_category": CATEGORY,
            "source": "OR-Bench-80k",
            "orginal_language": "en",
            "text_fr": "",
            "text_de": "",
            "text_en": text,
        })
print(f"Wrote {OUTPUT}")
