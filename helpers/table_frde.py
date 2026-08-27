"""Print the French/German refusal table (paper Table 1) from the master.

Reads results/master_long.csv (built by helpers/unify.py) and prints, per model
and topic, the refusal counts for the no-prefix baseline ("None") and the
supreme-court prefix ("Sup."), in French and German. Numbers are computed from
the data so the LaTeX table can be kept in sync.

Run from the repo root:  python helpers/table_frde.py
"""
import collections
import csv

MASTER = "results/master_long.csv"

MODELS = {
    "llama3.1:8b": "Llama 3.1 8B",
    "gemma4:e4b": "Gemma 4 E4B",
    "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M": "Apertus 8B",
    "qwen3:8b": "Qwen 3 8B",
}
TOPICS = ["violence", "sexual", "harmful", "unethical", "illegal"]
TOPIC_LABELS = {"violence": "Viol.", "sexual": "Sex.", "harmful": "Harm.",
                "unethical": "Uneth.", "illegal": "Illeg."}


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def load_counts():
    """counts[(model, topic, lang, prefix)] = refusals."""
    counts = collections.Counter()
    with open(MASTER, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["lang"] not in ("fr", "de") or _truthy(r["is_error"]):
                continue
            if r["prefix"] not in ("none", "supreme-court"):
                continue
            if _truthy(r["is_refused"]):
                counts[(r["model"], r["topic"], r["lang"], r["prefix"])] += 1
    return counts


def main() -> None:
    c = load_counts()
    header = f"{'Model':<13}{'Topic':<8}{'FR None':>9}{'FR Sup':>9}{'DE None':>9}{'DE Sup':>9}"
    print(header)
    print("-" * len(header))
    for model_key, label in MODELS.items():
        for i, t in enumerate(TOPICS):
            cells = (
                c[(model_key, t, "fr", "none")],
                c[(model_key, t, "fr", "supreme-court")],
                c[(model_key, t, "de", "none")],
                c[(model_key, t, "de", "supreme-court")],
            )
            name = label if i == 0 else ""
            print(f"{name:<13}{TOPIC_LABELS[t]:<8}" + "".join(f"{v:>9}" for v in cells))
        print()


if __name__ == "__main__":
    main()
