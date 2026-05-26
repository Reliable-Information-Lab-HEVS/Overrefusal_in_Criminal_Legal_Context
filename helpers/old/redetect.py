#!/usr/bin/env python3
"""Re-run keyword refusal detection on existing result CSVs.

Rewrites is_refused in place, on the FULL response (or preview if full missing),
using the current refusal_keywords.json. Preserves all other columns.

Usage:
    python redetect.py results/*.csv
"""
import csv, sys, shutil
from over_refusal.detector import RefusalDetector

detector = RefusalDetector()

def redetect_one(path):
    # Read original
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if "is_refused" not in fieldnames:
        print(f"  SKIP {path}: no is_refused column")
        return 0, 0
    # Re-detect
    changed = 0
    for r in rows:
        # Prefer the full response, fall back to preview
        text = r.get("response_full") or r.get("response_preview") or ""
        if not text or r.get("is_error","").strip().lower() == "true":
            continue
        lang = r.get("lang","en").strip() or "en"
        new = detector.is_refusal(text, lang)
        old = r["is_refused"].strip().lower() == "true"
        if new != old:
            changed += 1
        r["is_refused"] = "True" if new else "False"
    # Backup, then overwrite
    shutil.copy(path, path + ".bak")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return changed, len(rows)

paths = sys.argv[1:]
if not paths:
    print("Usage: python redetect.py <file1.csv> [file2.csv ...]")
    sys.exit(1)

total_changed = total_rows = 0
for p in paths:
    print(f"Processing {p}")
    c, n = redetect_one(p)
    print(f"  changed {c}/{n} rows")
    total_changed += c
    total_rows += n
print(f"\nTotal: {total_changed}/{total_rows} rows updated")
