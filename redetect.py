#!/usr/bin/env python3
"""
redetect.py — Recalcule la colonne `is_refused` d'un CSV de résultats déjà
généré, SANS relancer le moindre appel au modèle.

À utiliser quand les mots-clés (data/refusal_keywords.json) ou le détecteur
(over_refusal/detector.py, p. ex. OPENING_WINDOW_CHARS) ont changé après un run :
run_tf.py ne sait que reprendre des appels manquants, il dit « rien à faire »
dès que toutes les réponses sont là.

Exemples :
  # écrase le fichier, avec sauvegarde .bak automatique
  python redetect.py --in results/tf_2cond_apertus.csv

  # écrit ailleurs, laisse l'original intact
  python redetect.py --in results/tf_2cond_apertus.csv --out results/tf_2cond_apertus_redetect.csv

  # voir ce que ça changerait sans rien écrire
  python redetect.py --in results/tf_2cond_apertus.csv --dry-run

  # tout le texte au lieu des 300 premiers caractères
  python redetect.py --in results/tf_2cond_apertus.csv --full-text
"""
import argparse
import csv
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

from over_refusal.detector import RefusalDetector, OPENING_WINDOW_CHARS

csv.field_size_limit(10**8)


def main():
    ap = argparse.ArgumentParser(
        description="Recalcule is_refused sur un CSV de résultats existant (aucun appel LLM).")
    ap.add_argument("--in", dest="inp", required=True, help="CSV de résultats (sortie run_tf.py)")
    ap.add_argument("--out", default=None,
                    help="CSV de sortie (défaut : écrase l'entrée, avec .bak)")
    ap.add_argument("--dry-run", action="store_true", help="n'écrit rien, affiche juste le delta")
    ap.add_argument("--full-text", action="store_true",
                    help="scanne toute la réponse au lieu des %d premiers caractères"
                         % OPENING_WINDOW_CHARS)
    ap.add_argument("--opening-chars", type=int, default=None,
                    help="fenêtre d'ouverture personnalisée (prioritaire sur --full-text)")
    ap.add_argument("--show", type=int, default=10,
                    help="nb d'exemples de lignes qui changent à afficher (défaut 10)")
    args = ap.parse_args()

    inp = Path(args.inp)
    if not inp.exists():
        sys.exit(f"[STOP] introuvable : {inp}")

    if args.opening_chars is not None:
        window = args.opening_chars
    elif args.full_text:
        window = None
    else:
        window = OPENING_WINDOW_CHARS

    with open(inp, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)

    if not rows:
        sys.exit(f"[STOP] {inp} est vide.")
    if "response_full" not in fields or "is_refused" not in fields:
        sys.exit(f"[STOP] colonnes attendues absentes. Trouvé : {fields}")

    detector = RefusalDetector()
    changed = []
    flips = Counter()          # ("True->False", ...)
    per_key = defaultdict(lambda: [0, 0])   # (model, lang, task_variant) -> [refus, total]
    skipped_errors = 0

    for i, r in enumerate(rows, start=2):   # +2 = ligne du fichier (en-tête = 1)
        if (r.get("is_error") or "").strip() == "True":
            skipped_errors += 1
            continue
        old = (r.get("is_refused") or "").strip() == "True"
        new = detector.is_refusal(r.get("response_full") or "", r.get("lang") or "en",
                                  opening_chars=window)
        if new != old:
            flips[f"{old}->{new}"] += 1
            changed.append((i, r, old, new))
        r["is_refused"] = str(new)
        k = (r.get("model", ""), r.get("lang", ""), r.get("task_variant", ""))
        per_key[k][1] += 1
        per_key[k][0] += int(new)

    total_valid = sum(v[1] for v in per_key.values())
    total_ref = sum(v[0] for v in per_key.values())

    print(f"[i] {inp}")
    print(f"[i] fenêtre de détection : {'texte complet' if window is None else str(window) + ' car.'}")
    print(f"[i] {len(rows)} lignes | {skipped_errors} en erreur (ignorées) | {total_valid} exploitables")
    print(f"[i] changements : {dict(flips) or 'aucun'}")
    print(f"[i] taux de refus après recalcul : {total_ref}/{total_valid} "
          f"({total_ref / total_valid * 100:.1f}%)" if total_valid else "")

    print("\n=== refus par modèle / condition / langue ===")
    for (model, lang, var), (ref, tot) in sorted(per_key.items()):
        print(f"  {model:55s} {var:20s} {lang}  {ref:4d}/{tot:4d}  {ref / tot * 100:5.1f}%")

    if changed and args.show:
        print(f"\n=== {min(args.show, len(changed))} exemple(s) de lignes qui changent ===")
        for line_no, r, old, new in changed[:args.show]:
            head = (r.get("response_full") or "")[:160].replace("\n", " ")
            print(f"  L{line_no} {r['prompt_id']} | {r['lang']} | {old} -> {new}\n      {head}")

    if args.dry_run:
        print("\n[i] --dry-run : rien écrit.")
        return

    out = Path(args.out) if args.out else inp
    if out == inp:
        bak = inp.with_suffix(inp.suffix + ".bak")
        shutil.copy2(inp, bak)
        print(f"\n[i] sauvegarde : {bak}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"[✓] écrit : {out}")


if __name__ == "__main__":
    main()
