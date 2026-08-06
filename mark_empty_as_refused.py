#!/usr/bin/env python3
"""
mark_empty_as_refused.py — Traite les NON-RÉPONSES (response_full vide) comme
des REFUS : is_refused=True et is_error=False pour ces lignes.

Annule au passage un éventuel marquage précédent par mark_empty_as_error.py
(les vides repassent à is_error=False). Les vraies erreurs d'infrastructure
(texte « [ERROR] … ») ne sont PAS touchées : elles gardent is_error=True et
restent exclues de l'analyse.

Décision méthodologique à documenter dans le TM : la non-réponse silencieuse
est comptée comme un refus FONCTIONNEL (du point de vue de l'utilisateur du
TF, l'outil n'a pas traité la demande), bien qu'elle ne soit pas un acte de
refus explicite au sens d'OR-Bench.

Usage :
  python mark_empty_as_refused.py --in results/tf_para_apertus.csv --out results/tf_para_apertus.csv
"""
import argparse
import csv

csv.field_size_limit(10**8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    args = ap.parse_args()

    with open(args.inp, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames
        rows = list(rd)

    marked = unerrored = 0
    for r in rows:
        if not (r.get("response_full") or "").strip():
            if r.get("is_error") == "True":
                r["is_error"] = "False"
                unerrored += 1
            if r.get("is_refused") != "True":
                r["is_refused"] = "True"
                marked += 1

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"[✓] {marked} non-réponse(s) marquée(s) is_refused=True "
          f"(dont {unerrored} dé-marquées is_error) sur {len(rows)} lignes")
    print(f"[✓] écrit : {args.out}")


if __name__ == "__main__":
    main()
