#!/usr/bin/env python3
"""McNemar exact test on paired refusal data (baseline 'none' vs each prefix).

Pools across topics {violence, sexual, harmful, unethical, illegal} per model,
pairs each prompt's baseline ('none') refusal outcome with its prefixed-condition
outcome by prompt_id (inner join), and computes McNemar's exact test.

Refusal definition: a prompt counts as refused if EITHER the keyword detector
flagged it (is_refused in orbench_<topic>200_all.csv) OR the LLM judge labeled
it a direct refusal (judge_label == "direct_refusal" in
../LLM-as-a-judge-final-aggregated-results/judge_master_long.csv, lang == "en").
Judge coverage is joined on (model, condition, base prompt_id); rows with no
matching judge verdict fall back to the keyword flag alone.
"""
import csv
import os
from collections import defaultdict

from scipy.stats import binomtest

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
JUDGE_PATH = os.path.join(
    DATA_DIR, "..", "LLM-as-a-judge-final-aggregated-results", "judge_master_long.csv"
)
TOPICS = ["violence", "sexual", "harmful", "unethical", "illegal"]
# user-facing prefix name -> actual value in the 'condition' column
PREFIXES = {"lawyer": "lawyer", "supreme": "supreme-court", "jailbreak": "jailbreak"}
BASELINE = "none"


def to_bool(s):
    return str(s).strip().lower() == "true"


def load_judge_direct_refusals():
    """Return set of (model, condition, base_prompt_id) labeled direct_refusal, lang=en."""
    direct = set()
    with open(JUDGE_PATH, encoding="utf-8") as fh:
        fh.readline()  # header
        for line in fh:
            raw = line.rstrip("\n")
            if raw.startswith('"') and raw.endswith('";'):
                content = raw[1:-2].replace('""', '"')
            else:
                content = raw.rstrip(";")
            parts = content.split(",", 8)
            if len(parts) != 9:
                continue
            prompt_id, category, task_variant, lang, model, is_refused_kw, judge, judge_label, judge_reason = parts
            prompt_id = prompt_id.lstrip('"')
            if lang != "en" or judge_label != "direct_refusal":
                continue
            if "__" not in prompt_id:
                continue
            base_id, suffix = prompt_id.split("__", 1)
            direct.add((model, suffix, base_id))
    return direct


def load_rows(judge_direct):
    """rows[model][condition][prompt_id] = is_refused (bool), skipping is_error rows."""
    rows = defaultdict(lambda: defaultdict(dict))
    dropped_errors = 0
    judge_augmented = 0
    for topic in TOPICS:
        path = os.path.join(DATA_DIR, f"orbench_{topic}200_all.csv")
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if to_bool(row["is_error"]):
                    dropped_errors += 1
                    continue
                model = row["model"]
                condition = row["condition"]
                pid = row["prompt_id"]
                refused = to_bool(row["is_refused"])
                if not refused and (model, condition, pid) in judge_direct:
                    refused = True
                    judge_augmented += 1
                rows[model][condition][pid] = refused
    return rows, dropped_errors, judge_augmented


def main():
    judge_direct = load_judge_direct_refusals()
    rows, dropped_errors, judge_augmented = load_rows(judge_direct)
    models = sorted(rows.keys())

    results = []
    for model in models:
        baseline_map = rows[model].get(BASELINE, {})
        for prefix_label, prefix_value in PREFIXES.items():
            prefix_map = rows[model].get(prefix_value, {})

            baseline_ids = set(baseline_map)
            prefix_ids = set(prefix_map)
            paired_ids = baseline_ids & prefix_ids
            dropped_baseline_only = len(baseline_ids - prefix_ids)
            dropped_prefix_only = len(prefix_ids - baseline_ids)

            b = 0  # refused under prefix but not baseline
            c = 0  # refused under baseline but not prefix
            base_refused = 0
            prefix_refused = 0
            n = len(paired_ids)

            for pid in paired_ids:
                base_r = baseline_map[pid]
                pref_r = prefix_map[pid]
                if base_r:
                    base_refused += 1
                if pref_r:
                    prefix_refused += 1
                if pref_r and not base_r:
                    b += 1
                elif base_r and not pref_r:
                    c += 1

            if b + c > 0:
                pval = binomtest(b, b + c, 0.5, alternative="greater").pvalue
            else:
                pval = float("nan")

            odds_ratio = (b / c) if c > 0 else float("inf") if b > 0 else float("nan")

            base_rate = base_refused / n if n else float("nan")
            prefix_rate = prefix_refused / n if n else float("nan")

            results.append(
                {
                    "model": model,
                    "prefix": prefix_label,
                    "n_pairs": n,
                    "dropped_baseline_only": dropped_baseline_only,
                    "dropped_prefix_only": dropped_prefix_only,
                    "b_refused_prefix_not_baseline": b,
                    "c_refused_baseline_not_prefix": c,
                    "odds_ratio_b_over_c": odds_ratio,
                    "p_value_mcnemar_exact": pval,
                    "baseline_refusal_rate": base_rate,
                    "baseline_refused_n": base_refused,
                    "prefix_refusal_rate": prefix_rate,
                    "prefix_refused_n": prefix_refused,
                }
            )

    # Print report
    print(f"Dropped rows due to is_error=true (across all topics/models/conditions): {dropped_errors}")
    print(f"Rows flipped False->True by judge direct_refusal: {judge_augmented}\n")

    header = (
        f"{'model':<55} {'prefix':<10} {'n':>5} {'drop_b':>7} {'drop_p':>7} "
        f"{'b':>4} {'c':>4} {'OR(b/c)':>9} {'p-value':>12} "
        f"{'base_rate':>10} {'prefix_rate':>12}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        or_str = "inf" if r["odds_ratio_b_over_c"] == float("inf") else (
            "nan" if r["odds_ratio_b_over_c"] != r["odds_ratio_b_over_c"] else f"{r['odds_ratio_b_over_c']:.3f}"
        )
        p_str = "nan" if r["p_value_mcnemar_exact"] != r["p_value_mcnemar_exact"] else f"{r['p_value_mcnemar_exact']:.3e}"
        print(
            f"{r['model']:<55} {r['prefix']:<10} {r['n_pairs']:>5} "
            f"{r['dropped_baseline_only']:>7} {r['dropped_prefix_only']:>7} "
            f"{r['b_refused_prefix_not_baseline']:>4} {r['c_refused_baseline_not_prefix']:>4} "
            f"{or_str:>9} {p_str:>12} "
            f"{r['baseline_refusal_rate']*100:>9.1f}% {r['prefix_refusal_rate']*100:>11.1f}%"
        )

    # Also write a CSV for downstream use
    out_path = os.path.join(DATA_DIR, "mcnemar_results.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
