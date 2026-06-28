import csv

SRC  = "data/bger_para_ALL.csv"        # ton nouveau découpage
OUT  = "data/bger_para_missing.csv"
KEEP = ("bgr_09", "bgr_14")

with open(SRC, encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames
    rows = [r for r in reader
            if (r.get("prompt_id") or "").rsplit("_p", 1)[0] in KEEP]

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)

print(f"{len(rows)} lignes -> {OUT}")
print("arrêts:", sorted({r['prompt_id'].rsplit('_p', 1)[0] for r in rows}))