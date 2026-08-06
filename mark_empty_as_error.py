#!/usr/bin/env python3
"""
mark_empty_as_error.py — Passe is_error à True pour les lignes SANS réponse
(response_full vide) dans un CSV de résultats run_tf.

Intérêt : un simple filtre is_error != True suffit alors à obtenir les données
exploitables (utile pour l'annexe du TM et pour l'équipe du TF), sans connaître
la subtilité des « non-réponses silencieuses » d'Apertus.

La distinction reste lisible dans le fichier :
  - is_error=True + response_full commençant par « [ERROR] »  -> erreur
    d'infrastructure (timeout, connexion) ;
  - is_error=True + response_full VIDE -> non-réponse silencieuse du modèle
    (comportement, pas une panne). response_full n'est pas modifié.

⚠️ Effet de bord voulu : si tu relances run_tf sur ce fichier, ces cellules
   seront RETENTÉES (les erreurs le sont à la reprise). Pour Apertus c'est
   généralement sans issue (vide déterministe à température 0) — ne relance
   pas après marquage, ou accepte quelques tentatives perdues.

Usage :
  python mark_empty_as_error.py --in results/tf_para_apertus.csv --out results/tf_para_apertus.csv
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

    marked = already = 0
    for r in rows:
        if not (r.get("response_full") or "").strip():
            if r.get("is_error") == "True":
                already += 1
            else:
                r["is_error"] = "True"
                marked += 1

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"[✓] {marked} non-réponse(s) marquée(s) is_error=True "
          f"({already} déjà marquées) sur {len(rows)} lignes")
    print(f"[✓] écrit : {args.out}")


if __name__ == "__main__":
    main()
