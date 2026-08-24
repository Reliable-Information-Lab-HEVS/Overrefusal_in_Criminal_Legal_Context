#!/usr/bin/env python3
"""Apply Holm-Bonferroni correction to the 12 McNemar p-values (4 models x 3 prefixes)."""
import csv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IN_PATH = os.path.join(BASE_DIR, "english", "mcnemar_results.csv")
OUT_PATH = os.path.join(BASE_DIR, "mcnemar_appendix.csv")

MODEL_ORDER = [
    "llama3.1:8b",
    "gemma4:e4b",
    "qwen3:8b",
    "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M",
]
PREFIX_ORDER = ["lawyer", "supreme", "jailbreak"]


def holm_bonferroni(pvals):
    """Return Holm-adjusted p-values, same order as input."""
    m = len(pvals)
    indexed = sorted(range(m), key=lambda i: pvals[i])
    adjusted = [None] * m
    running_max = 0.0
    for rank, idx in enumerate(indexed):
        adj = (m - rank) * pvals[idx]
        running_max = max(running_max, adj)
        adjusted[idx] = min(running_max, 1.0)
    return adjusted


def main():
    with open(IN_PATH, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    row_by_key = {(r["model"], r["prefix"]): r for r in rows}
    ordered_rows = [row_by_key[(m, p)] for m in MODEL_ORDER for p in PREFIX_ORDER]

    pvals = [float(r["p_value_mcnemar_exact"]) for r in ordered_rows]
    p_holm = holm_bonferroni(pvals)

    out_rows = []
    for r, ph in zip(ordered_rows, p_holm):
        out_rows.append(
            {
                "model": r["model"],
                "prefix": r["prefix"],
                "b": r["b_refused_prefix_not_baseline"],
                "c": r["c_refused_baseline_not_prefix"],
                "odds_ratio": r["odds_ratio_b_over_c"],
                "rate_baseline": r["baseline_refusal_rate"],
                "rate_prefix": r["prefix_refusal_rate"],
                "p_uncorrected": r["p_value_mcnemar_exact"],
                "p_holm": f"{ph:.6e}",
            }
        )

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    header = (
        f"{'model':<55} {'prefix':<10} {'b':>4} {'c':>4} {'OR':>9} "
        f"{'rate_base':>10} {'rate_pfx':>10} {'p_uncorr':>12} {'p_holm':>12}"
    )
    print(header)
    print("-" * len(header))
    for r in out_rows:
        or_val = float(r["odds_ratio"])
        or_str = "inf" if or_val == float("inf") else f"{or_val:.3f}"
        print(
            f"{r['model']:<55} {r['prefix']:<10} {r['b']:>4} {r['c']:>4} {or_str:>9} "
            f"{float(r['rate_baseline'])*100:>9.1f}% {float(r['rate_prefix'])*100:>9.1f}% "
            f"{float(r['p_uncorrected']):>12.3e} {float(r['p_holm']):>12.3e}"
        )

    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
