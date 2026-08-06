#!/usr/bin/env python3
"""
dedup_results.py — Supprime les lignes surnuméraires d'un CSV de résultats
(run_tf.py / run_judge.py) : ne garde que la DERNIÈRE tentative par clé
(prompt_id, lang, model), dans l'ordre de première apparition des clés.

Les anciennes tentatives (erreurs retentées) sont retirées ; la dernière
tentative reste, même si c'est une erreur ou une réponse vide (l'analyse les
exclut, et la reprise de run_tf retentera les erreurs restantes).

⚠️ À lancer uniquement quand le run correspondant est TERMINÉ (pas pendant
   qu'un run écrit encore dans le fichier).

Usage :
  python dedup_results.py --in results/tf_2cond_apertus.csv --out results/tf_2cond_apertus.csv
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

    order, last = [], {}
    for r in rows:
        k = (r["prompt_id"], r["lang"], r["model"])
        if k not in last:
            order.append(k)
        last[k] = r                      # la dernière occurrence gagne

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(last[k] for k in order)

    print(f"[✓] {len(rows)} lignes -> {len(order)} clés uniques "
          f"({len(rows)-len(order)} lignes surnuméraires retirées)")
    print(f"[✓] écrit : {args.out}")


if __name__ == "__main__":
    main()
