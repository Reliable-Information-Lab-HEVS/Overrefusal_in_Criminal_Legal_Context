#!/usr/bin/env python3
"""Apertus refusal rates: rows = topics, cols = prefix conditions."""
import csv, os

TOPICS = ["violence", "sexual", "harmful", "illegal"]
VARIANTS = [
    ("none",          ""),
    ("lawyer",        "_p2_lawyer"),
    ("supreme_court", "_prefix"),
    ("jailbreak",     "_p3_jailbreak"),
]

def count_refusals(path):
    if not os.path.exists(path):
        return None, None
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    ref = sum(1 for r in rows if r["is_refused"].strip().lower() == "true")
    return ref, len(rows)

print(f"\n{'APERTUS — refusal counts (refused/total)':}")
header = f"{'topic':<10}" + "".join(f"{n:>16}" for n,_ in VARIANTS)
print(header)
print("-" * len(header))
for t in TOPICS:
    row = f"{t:<10}"
    for _, suffix in VARIANTS:
        path = f"results/orbench_{t}200{suffix}_apertus_results.csv"
        ref, tot = count_refusals(path)
        cell = f"{ref}/{tot}" if ref is not None else "MISSING"
        row += f"{cell:>16}"
    print(row)
