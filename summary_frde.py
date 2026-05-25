"""For each topic, build a wide CSV of prompts with at least one refusal,
showing the response text from every (model, lang, variant) cell."""
import csv, os

TOPICS = ["violence","sexual","harmful","unethical","illegal"]
INPUT_DIR  = "results/french_german"
OUTPUT_DIR = "results/french_german/refusal_matrices"
os.makedirs(OUTPUT_DIR, exist_ok=True)

SHORT = {
    "gemma4:e4b": "GM",
    "qwen3:8b": "QW",
    "llama3.1:8b": "LL",
    "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M": "AP",
}
MODELS  = ["LL","GM","AP","QW"]
LANGS   = ["fr","de"]
VARIANTS = ["normal","hard"]
PREVIEW_LEN = 500   # chars per response; raise/lower if you want

for topic in TOPICS:
    in_path  = f"{INPUT_DIR}/orbench_{topic}200_frde_all.csv"
    out_path = f"{OUTPUT_DIR}/{topic}_refusals.csv"
    if not os.path.exists(in_path):
        print(f"MISSING: {in_path}"); continue

    pivot = {}        # prompt_id -> {(model, lang, variant): (flag, text)}
    prompt_fr = {}    # prompt_id -> French no-prefix prompt text

    for r in csv.DictReader(open(in_path, encoding="utf-8")):
        pid = r["prompt_id"]
        m = SHORT.get(r["model"], r["model"][:6])
        key = (m, r["lang"], r["task_variant"])
        if r.get("is_error","").strip().lower()=="true":
            flag = "!"
        elif r["is_refused"].strip().lower()=="true":
            flag = "R"
        else:
            flag = "."
        text = (r.get("response_full") or r.get("response_preview","")).strip().replace("\n"," ")[:PREVIEW_LEN]
        pivot.setdefault(pid, {})[key] = (flag, text)
        if r["lang"]=="fr" and r["task_variant"]=="normal" and pid not in prompt_fr:
            prompt_fr[pid] = r["prompt"][:300].replace("\n"," ")

    # cell order: model × lang × variant
    cells = [(m,l,v) for m in MODELS for l in LANGS for v in VARIANTS]
    header = ["prompt_id","fr_prompt"]
    for m,l,v in cells:
        header += [f"{m}_{l}_{v}_flag", f"{m}_{l}_{v}_response"]

    n = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header)
        for pid in sorted(pivot):
            if not any(v[0]=="R" for v in pivot[pid].values()):
                continue
            row = [pid, prompt_fr.get(pid,"")]
            for c in cells:
                flag, txt = pivot[pid].get(c, ("-",""))
                row += [flag, txt]
            w.writerow(row)
            n += 1
    print(f"{topic}: {n} prompts with at least one refusal → {out_path}")