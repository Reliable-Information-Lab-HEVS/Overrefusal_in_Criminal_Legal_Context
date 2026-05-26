#!/usr/bin/env python3
"""Build a master long-format CSV from all results, plus print summary."""
import csv, os, glob

TOPICS = ["violence", "sexual", "harmful", "unethical", "illegal"]
COND_SUFFIXES = {
    "none":          "",
    "supreme_court": "_prefix",
    "lawyer":        "_p2_lawyer",
    "jailbreak":     "_p3_jailbreak",
}

def load(path, topic, condition):
    if not os.path.exists(path):
        return []
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        # normalize prompt_id to base (strip prefix suffixes)
        pid = r["prompt_id"]
        for s in ("_prefix","_p2_lawyer","_p3_jailbreak"):
            pid = pid.replace(s, "")
        out.append({
            "topic": topic,
            "condition": condition,
            "model": r["model"],
            "prompt_id": pid,
            "is_refused": r["is_refused"].strip().lower() == "true",
            "is_error": r.get("is_error","").strip().lower() == "true",
            "response_preview": r.get("response_preview", ""),
        })
    return out

rows = []
for topic in TOPICS:
    for cond, suffix in COND_SUFFIXES.items():
        base = f"results/orbench_{topic}200{suffix}"
        # Multi-model file (llama+gemma+qwen, all in one)
        rows += load(f"{base}_results.csv", topic, cond)
        # Apertus separate file
        rows += load(f"{base}_apertus_results.csv", topic, cond)
        # Llama-only fill file (illegal-only for now)
        rows += load(f"{base}_llama_results.csv", topic, cond)

# Write master
with open("results/master_long.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"Wrote results/master_long.csv ({len(rows)} rows)")

# --- Summary: per model, topic x condition refusal counts ---
from collections import defaultdict
counts = defaultdict(lambda: [0, 0])   # (model,topic,cond) -> [refused, total]
for r in rows:
    if r["is_error"]: continue
    k = (r["model"], r["topic"], r["condition"])
    counts[k][1] += 1
    if r["is_refused"]: counts[k][0] += 1

models = sorted({k[0] for k in counts})
conds  = list(COND_SUFFIXES)

for m in models:
    print(f"\n=== {m} — refused/total ===")
    header = f"{'topic':<11}" + "".join(f"{c:>16}" for c in conds)
    print(header)
    print("-" * len(header))
    for t in TOPICS:
        row = f"{t:<11}"
        for c in conds:
            ref, tot = counts.get((m,t,c), [0,0])
            row += f"{f'{ref}/{tot}' if tot else '-':>16}"
        print(row)
