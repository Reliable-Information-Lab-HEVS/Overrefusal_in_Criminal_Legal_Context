#!/usr/bin/env python3
"""Compare refusal with vs without the Tribunal prefix."""
import csv

PLAIN  = "results/sexual_50_results.csv"
PREFIX = "results/sexual_50_prefix_results.csv"

def load(path):
    """Return {(base_id, model): is_refused_bool}."""
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        pid = r["prompt_id"].replace("_prefix", "")   # normalize to base id
        model = r["model"]
        refused = r["is_refused"].strip().lower() == "true"
        out[(pid, model)] = refused
    return out

plain  = load(PLAIN)
prefix = load(PREFIX)

# --- Summary counts per model ---
models = sorted({m for (_, m) in plain})
print("=== SUMMARY ===")
for m in models:
    p_ref = sum(1 for (pid, mm), v in plain.items()  if mm == m and v)
    x_ref = sum(1 for (pid, mm), v in prefix.items() if mm == m and v)
    p_tot = sum(1 for (pid, mm) in plain  if mm == m)
    x_tot = sum(1 for (pid, mm) in prefix if mm == m)
    print(f"{m}:")
    print(f"  no prefix : {p_ref}/{p_tot} refused")
    print(f"  prefix    : {x_ref}/{x_tot} refused")
    print(f"  change    : {x_ref - p_ref:+d}")

# --- Per-prompt differences ---
print("\n=== PROMPTS THAT CHANGED ===")
changed = 0
for key in sorted(plain):
    if key not in prefix:
        continue
    before, after = plain[key], prefix[key]
    if before != after:
        changed += 1
        pid, model = key
        if before and not after:
            flip = "REFUSED -> answered  (prefix unlocked it)"
        else:
            flip = "answered -> REFUSED  (prefix triggered refusal)"
        print(f"  {pid} | {model} | {flip}")
if changed == 0:
    print("  (no prompts changed)")
print(f"\nTotal changed: {changed}")
