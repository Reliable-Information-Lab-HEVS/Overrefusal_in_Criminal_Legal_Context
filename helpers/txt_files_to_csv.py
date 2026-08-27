#!/usr/bin/env python3
"""Merge a folder of raw .txt documents into a prompts CSV compatible with
over_refusal/prompts.py (same minimal schema as the cleaned orbench_*200.csv
files: prompt_id, or_category, bger_source, orginal_language, text_en).

Only English is populated (text_fr/text_de/text_it are intentionally left
out; evaluation.py falls back to text_en for missing languages). Only *.txt
files are picked up, so OS artifacts (e.g. macOS .textClipping files) are
ignored automatically.

Usage:
    python helpers/txt_files_to_csv.py <folder> <or_category> <output_csv>

Each file's prompt_id is "<category>_<leading digits of filename>", e.g.
"swiss_defense_346" for "346 Switzerland Security Situation Report....txt".
"""

import csv
import re
import sys
from pathlib import Path


def build_csv(folder: str, category: str, output_csv: str) -> None:
    folder_path = Path(folder)
    txt_files = sorted(folder_path.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"No .txt files found in {folder}")

    rows = []
    for path in txt_files:
        m = re.match(r"(\d+)", path.stem)
        doc_id = m.group(1) if m else path.stem.replace(" ", "_")
        rows.append({
            "prompt_id": f"{category}_{doc_id}",
            "or_category": category,
            "bger_source": path.name,
            "orginal_language": "en",
            "text_en": path.read_text(encoding="utf-8", errors="ignore").strip(),
        })

    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["prompt_id", "or_category", "bger_source", "orginal_language", "text_en"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path}")
    for r in rows:
        print(f"  {r['prompt_id']:30s} <- {r['bger_source']} ({len(r['text_en'])} chars)")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    build_csv(sys.argv[1], sys.argv[2], sys.argv[3])
