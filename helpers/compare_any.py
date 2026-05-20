#!/usr/bin/env python3
"""Compare refusal with vs without prefix. Usage: edit PLAIN and PREFIX paths."""
import sys, csv

PLAIN  = sys.argv[1]
PREFIX = sys.argv[2]

def load(path):
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        pid = r["prompt_id"].replace("_prefix", "")
        out[(pid, r["model"])] = r["is_refused"].strip().lower() == "true"
    return out

plain, prefix = load(PLAIN), load(PREFIX)
models = sorted({m for (_, m) in plain})

print("=== SUMMARY ===")
for m in models:
    p = sum(1 for (pid, mm), v in plain.items()  if mm == m and v)
    x = sum(1 for (pid, mm), v in prefix.items() if mm == m and v)
    pt = sum(1 for (pid, mm) in plain  if mm == m)
    xt = sum(1 for (pid, mm) in prefix if mm == m)
    print(f"{m}:  no-prefix {p}/{pt}   prefix {x}/{xt}   change {x-p:+d}")

print("\n=== PROMPTS THAT CHANGED ===")
changed = 0
for key in sorted(plain):
    if key not in prefix or plain[key] == prefix[key]:
        continue
    changed += 1
    pid, model = key
    flip = ("REFUSED -> answered (prefix unlocked)" if plain[key]
            else "answered -> REFUSED (prefix triggered)")
    print(f"  {pid} | {model} | {flip}")
print(f"\nTotal changed: {changed}")
