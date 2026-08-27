#!/usr/bin/env python3
"""Split one raw .txt document into page-sized blocks and write a prompts CSV
compatible with over_refusal/prompts.py (same minimal schema as
txt_files_to_csv.py, but one row per page instead of one row per file).

Pages are split on form-feed characters (\\f), which most PDF-to-text
exporters emit at each original page boundary -- so this reproduces the
source document's own pagination instead of an arbitrary character count.
Pages shorter than --min-chars (after stripping) are dropped as blank/divider
pages (e.g. section-break or page-number-only pages) rather than kept as
near-empty prompts.

Only the given --lang column is populated (task_* columns are left empty;
evaluation.py/prompts.py glue task+text and fall back to text-only when task
is empty, and the prefix system supplies its own task wording e.g.
"Extract the key facts... from the following document:").

Usage:
    python helpers/txt_pages_to_csv.py <input.txt> <or_category> <output_csv> [--lang de] [--min-chars 50]
"""

import argparse
import csv
from pathlib import Path


def split_pages(text: str, min_chars: int) -> list:
    pages = [p.strip() for p in text.split("\f")]
    return [p for p in pages if len(p) >= min_chars]


def build_csv(input_txt: str, category: str, output_csv: str, lang: str, min_chars: int) -> None:
    in_path = Path(input_txt)
    text = in_path.read_text(encoding="utf-8", errors="ignore")
    pages = split_pages(text, min_chars)
    if not pages:
        raise ValueError(f"No pages >= {min_chars} chars found in {input_txt}")

    text_col = f"text_{lang}"
    fieldnames = ["prompt_id", "or_category", "bger_source", "orginal_language", text_col]

    rows = []
    width = len(str(len(pages)))
    for i, page in enumerate(pages, start=1):
        rows.append({
            "prompt_id": f"{category}_{i:0{width}d}",
            "or_category": category,
            "bger_source": f"{in_path.name} (page {i}/{len(pages)})",
            "orginal_language": lang,
            text_col: page,
        })

    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path} (dropped {len(text.split(chr(0x0c))) - len(pages)} pages < {min_chars} chars)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_txt", help="Path to the source .txt file")
    parser.add_argument("category", help="or_category value, also used as the prompt_id prefix")
    parser.add_argument("output_csv", help="Path to write the prompts CSV")
    parser.add_argument("--lang", default="de", choices=["fr", "de", "it", "en"],
                         help="Language column to populate (default: de)")
    parser.add_argument("--min-chars", type=int, default=50,
                         help="Drop pages shorter than this after stripping (default: 50)")
    args = parser.parse_args()
    build_csv(args.input_txt, args.category, args.output_csv, args.lang, args.min_chars)
