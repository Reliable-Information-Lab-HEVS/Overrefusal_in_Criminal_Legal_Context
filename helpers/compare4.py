#!/usr/bin/env python3
"""Compare 4 conditions: none / lawyer / supreme court / jailbreak."""
import csv

FILES = [
    ("none",         "results/orbench_sexual200_results.csv"),
    ("lawyer",       "results/orbench_sexual200_p2_lawyer_results.csv"),
    ("supreme_court","results/orbench_sexual200_prefix_results.csv"),
    ("jailbreak",    "results/orbench_sexual200_p3_jailbreak_results.csv"),
]

def load(path):
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        # strip any prefix suffix to get the base prompt id
        pid = r["prompt_id"]
        for s in ("_p2_lawyer","_p3_jailbreak","_prefix"):
            pid = pid.replace(s, "")
        out[(pid, r["model"])] = r["is_refused"].strip().lower() == "true"
    return out

data = {name: load(path) for name, path in FILES}
models = sorted({m for (_, m) in data["none"]})

# --- SUMMARY ---
print("=== REFUSAL COUNTS (out of 200) ===")
header = f"{'model':<16}" + "".join(f"{n:>16}" for n,_ in FILES)
print(header)
for m in models:
    row = f"{m:<16}"
    for name,_ in FILES:
        ref = sum(1 for (pid,mm),v in data[name].items() if mm==m and v)
        tot = sum(1 for (pid,mm) in data[name] if mm==m)
        row += f"{f'{ref}/{tot}':>16}"
    print(row)

# --- PER-PROMPT ---
print("\n=== PER-PROMPT REFUSAL PATTERN ===")
print("(R = refused, . = answered)  order: none lawyer supreme jailbreak")
all_keys = sorted(data["none"])
for key in all_keys:
    pattern = ""
    for name,_ in FILES:
        v = data[name].get(key)
        pattern += "R" if v else ("." if v is False else "?")
    if "R" in pattern:   # only show prompts with at least one refusal
        pid, model = key
        print(f"  {pid} | {model:<14} {pattern}")
