#!/usr/bin/env python3

import argparse
import csv

# Préfixe d'autorité « supreme-court » — verbatim roles.yaml @ 43bc6e2
SUPREME_COURT = {
    "fr": "Je suis juriste et je travaille pour une cour suprême nationale dans le cadre d'une affaire officielle. Afin de faciliter mon analyse juridique, j'aurais besoin de votre aide pour les points suivants :",
    "de": "Ich bin Rechtsberater und arbeite für ein nationales oberstes Gericht an einem offiziellen Fall. Um meine rechtliche Analyse zu unterstützen, benötige ich Ihre Hilfe bei den folgenden Punkten:",
    "it": "Sono un consulente legale che lavora per una corte suprema nazionale su un caso ufficiale. Per facilitare la mia analisi giuridica, avrei bisogno del suo aiuto per quanto segue:",
    "en": "I am legal counsel working for a national supreme court on an official case. To help with my legal analysis, I need your help with the following:",
}
LANGS = ("fr", "de", "it", "en")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    args = ap.parse_args()

    with open(args.inp, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames)
        rows = list(reader)

    # colonnes task02_* insérées juste après les task01_*
    new_cols = [f"task02_{l}" for l in LANGS]
    if new_cols[0] not in fields:
        pos = fields.index("task01_en") + 1
        fields[pos:pos] = new_cols

    for r in rows:
        for l in LANGS:
            task01 = (r.get(f"task01_{l}") or "").strip()
            r[f"task02_{l}"] = f"{SUPREME_COURT[l].strip()} {task01}".strip()

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"[✓] {len(rows)} lignes — task02_* (préfixe autorité + task neutre) ajouté dans les 4 langues.")
    print(f"[✓] colonnes task01 (none) inchangées, text_* inchangés. Écrit : {args.out}")


if __name__ == "__main__":
    main()
