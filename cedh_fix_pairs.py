#!/usr/bin/env python3
"""
cedh_fix_pairs.py — Contrôle et corrige HORS LIGNE les paires bilingues du
dataset CEDH : détecte les text_fr qui ne sont PAS la traduction officielle du
même arrêt (autre document de la même affaire apparié par erreur via l'appno).

Méthode : les chiffres (années, jours) sont invariants entre langues. Pour
chaque § commun, on compare les ensembles de nombres EN vs FR ; si la
concordance moyenne est trop faible, le FR est un autre document -> on le VIDE
(il sera retraduit par DeepL depuis l'anglais, comme les monolingues).

Vérifie aussi que la catégorie reste attestée dans le texte EN (une mauvaise
paire peut avoir amputé l'anglais via l'intersection des §§) -> ces lignes
sont marquées _A_REMPLACER (à re-collecter ou supprimer).

Usage :
  python cedh_fix_pairs.py --in data/cedh_dataset.csv --out data/cedh_dataset.csv
"""

import argparse
import csv
import re

csv.field_size_limit(10**8)

VERIFY = {
    "sexual": re.compile(r"rape|sexual (abuse|assault|violence|intercourse)|\bviol(?!ation|ence|emment)\w*|abus sexuel|agression sexuelle|violences sexuelles", re.I),
    "violence": re.compile(r"torture|ill-?treat|beaten|stabbed|killed|murder|meurtre|mauvais traitements|coups|assassin", re.I),
    "self-harm": re.compile(r"suicide|hanged|self-?harm|automutilation|se pendre|s'est pendu", re.I),
    "illegal": re.compile(r"drug|trafficking|heroin|cocaine|money laundering|stupéfiants|blanchiment|criminal organi[sz]ation|organisation criminelle|héroïne|cocaïne", re.I),
}
NUMS = re.compile(r"\b\d{1,4}\b")


def para_nums(line):
    """Nombres d'un § (sans le numéro du § lui-même)."""
    body = line.split(".", 1)[1] if "." in line else line
    return set(NUMS.findall(body))


def pair_score(en, fr):
    """Concordance moyenne des nombres, § par §, sur les §§ où il y en a."""
    le, lf = en.split("\n"), fr.split("\n")
    scores = []
    for a, b in zip(le, lf):
        na, nb = para_nums(a), para_nums(b)
        if not na and not nb:
            continue
        scores.append(len(na & nb) / max(1, len(na | nb)))
    return sum(scores) / len(scores) if scores else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--threshold", type=float, default=0.55)
    args = ap.parse_args()

    with open(args.inp, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames
        rows = list(rd)

    dropped_fr, flagged = [], []
    for r in rows:
        if r["text_fr"].strip():
            s = pair_score(r["text_en"], r["text_fr"])
            if s < args.threshold:
                dropped_fr.append((r["prompt_id"], round(s, 2)))
                r["text_fr"] = ""          # FR d'un autre document -> retraduction DeepL
        if not VERIFY[r["category"]].search(r["text_en"] + " " + r["text_fr"]):
            flagged.append(r["prompt_id"])
            if "_A_REMPLACER" not in r["prompt_id"]:
                r["prompt_id"] += "_A_REMPLACER"

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"[✓] paires FR vidées (mauvais document apparié) : {len(dropped_fr)} {dropped_fr}")
    print(f"[✓] lignes _A_REMPLACER (catégorie non attestée dans le texte) : {len(flagged)} {flagged}")
    print(f"[✓] écrit : {args.out}")


if __name__ == "__main__":
    main()
