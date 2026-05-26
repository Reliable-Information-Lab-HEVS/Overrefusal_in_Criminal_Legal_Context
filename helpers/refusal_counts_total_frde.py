"""Recalculate FR/DE refusal counts from the consolidated files."""
import csv, os
from collections import defaultdict

TOPICS = ["violence","sexual","harmful","unethical","illegal"]
counts = defaultdict(lambda: [0,0])  # (lang, model, topic, variant) -> [refused, total]

for topic in TOPICS:
    path = f"results/french_german/orbench_{topic}200_frde_all.csv"
    if not os.path.exists(path):
        print(f"MISSING: {path}"); continue
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r.get("is_error","").strip().lower()=="true": continue
        k = (r["lang"], r["model"], topic, r["task_variant"])
        counts[k][1] += 1
        if r["is_refused"].strip().lower()=="true":
            counts[k][0] += 1

SHORT = {
    "llama3.1:8b": "Llama 3.1 8B",
    "gemma4:e4b": "Gemma 4 E4B",
    "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M": "Apertus 8B",
    "qwen3:8b": "Qwen 3 8B",
}
MODEL_ORDER = ["llama3.1:8b","gemma4:e4b","hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M","qwen3:8b"]

for lang in ["fr","de"]:
    print(f"\n=== {lang.upper()} ===")
    for m in MODEL_ORDER:
        print(f"  {SHORT[m]}")
        for t in TOPICS:
            n_r, n_t = counts.get((lang,m,t,"normal"),[0,0])
            h_r, h_t = counts.get((lang,m,t,"hard"),[0,0])
            n = f"{n_r}" if n_t else "-"
            h = f"{h_r}" if h_t else "-"
            print(f"    {t:<10} no_prefix {n:<5} supreme {h}")