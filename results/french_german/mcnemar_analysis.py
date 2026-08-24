#!/usr/bin/env python3
"""McNemar exact test on paired refusal data (baseline 'none' vs supreme-court
prefix), for French and German.

Pools across topics {violence, sexual, harmful, unethical, illegal} per
(model, lang), pairs each prompt's baseline ('none') refusal outcome with its
supreme-court-prefixed outcome by prompt_id (inner join), and computes
McNemar's exact test. Unlike English, French/German only have the
supreme-court prefix condition (no lawyer/jailbreak).

Refusal definition: a prompt counts as refused if EITHER the keyword detector
flagged it (is_refused_keyword) OR the LLM judge labeled it a direct refusal
(judge_label == "direct_refusal"). Both signals come from the same source,
../LLM-as-a-judge-final-aggregated-results/judge_master_long.csv.
"""
import csv
import os
from collections import defaultdict

from scipy.stats import binomtest

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
JUDGE_PATH = os.path.join(
    DATA_DIR, "..", "LLM-as-a-judge-final-aggregated-results", "judge_master_long.csv"
)
LANGS = ["fr", "de"]
BASELINE = "none"
PREFIX_LABEL = "supreme"
PREFIX_VALUE = "supreme-court"


def load_rows():
    """rows[(model, lang)][condition][prompt_id] = is_refused (bool)."""
    rows = defaultdict(lambda: defaultdict(dict))
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
            if lang not in LANGS or "__" not in prompt_id:
                continue
            base_id, suffix = prompt_id.split("__", 1)
            refused = (is_refused_kw == "True") or (judge_label == "direct_refusal")
            rows[(model, lang)][suffix][base_id] = refused
    return rows


def main():
    rows = load_rows()
    keys = sorted(rows.keys())

    results = []
    for model, lang in keys:
        baseline_map = rows[(model, lang)].get(BASELINE, {})
        prefix_map = rows[(model, lang)].get(PREFIX_VALUE, {})

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
                "lang": lang,
                "prefix": PREFIX_LABEL,
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

    header = (
        f"{'model':<55} {'lang':<5} {'prefix':<8} {'n':>5} {'drop_b':>7} {'drop_p':>7} "
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
            f"{r['model']:<55} {r['lang']:<5} {r['prefix']:<8} {r['n_pairs']:>5} "
            f"{r['dropped_baseline_only']:>7} {r['dropped_prefix_only']:>7} "
            f"{r['b_refused_prefix_not_baseline']:>4} {r['c_refused_baseline_not_prefix']:>4} "
            f"{or_str:>9} {p_str:>12} "
            f"{r['baseline_refusal_rate']*100:>9.1f}% {r['prefix_refusal_rate']*100:>11.1f}%"
        )

    out_path = os.path.join(DATA_DIR, "mcnemar_results.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
