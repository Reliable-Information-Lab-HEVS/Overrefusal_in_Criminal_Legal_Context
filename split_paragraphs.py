#!/usr/bin/env python3
"""Découpe les arrêts BGer en paragraphes — une ligne CSV par paragraphe.

Version adaptée au format canonique actuel (celui de data/bger_dataset.csv) :
  prompt_id, category, bger_source, bger_url,
  task01_<lang> [, task02_<lang>], orginal_language, text_<lang>

Règle (identique à l'ancienne, filtre renforcé séance 24) :
  - lignes non vides de chaque text_<lang> ;
  - garde-fou d'alignement : les 4 langues doivent avoir le MÊME nombre de
    lignes brutes, sinon l'arrêt est listé (point de divergence) et exclu ;
  - un indice de ligne est un paragraphe si sa longueur dépasse MIN_PARA_CHARS
    dans LES 4 LANGUES (min conjoint) → mêmes paragraphes partout par
    construction, et les titres courts (« A. », « B.c ») sont éliminés.

prompt_id de sortie : bgr_001 -> bgr_001_p01, bgr_001_p02, …
Les colonnes task01_*/task02_* sont recopiées telles quelles (le préfixe reste
appliqué par paragraphe via --task-mode all du runner).

Aperçu par défaut, écriture uniquement avec --write :
  python split_paragraphs.py --all --csv data/bger_dataset.csv
  python split_paragraphs.py --all --csv data/bger_dataset.csv --write
  python split_paragraphs.py --prompt-id bgr_002 --csv data/bger_dataset.csv
"""

import argparse
import csv
import re
import sys
from pathlib import Path

csv.field_size_limit(10**8)

LANGS = ["fr", "de", "it", "en"]
MIN_PARA_CHARS = 100   # défaut ; modifiable via --min-chars
META = ("category", "bger_source", "bger_url", "orginal_language")

# Garde anti-fragment : une ligne qui COMMENCE en minuscule ou par une
# ponctuation de continuation (, ; : . ) ]) est un morceau de phrase coupée
# (artefact de mise en page), pas un paragraphe. Jugé sur la langue d'origine.
FRAGMENT_START = re.compile(r'^[a-zà-öø-ÿ]|^[,;:.)\]]|^\'|^"?\.\s')


def load_rows(csv_path):
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        return rd.fieldnames, list(rd)


def task_cols(fields):
    """Toutes les colonnes task présentes (task01_*, task02_*, …), dans l'ordre."""
    return [c for c in fields if c.startswith("task")]


def nonblank_lines(text):
    return [s for s in (l.strip() for l in (text or "").split("\n")) if s]


def analyze(row, min_chars=MIN_PARA_CHARS, fragment_guard=True):
    """(paras par langue, comptes, aligné ?) — aligné par construction si OK.

    La décision de retenir un indice de ligne se prend UNE SEULE FOIS, sur la
    LANGUE D'ORIGINE de l'arrêt (le texte authentique), puis s'applique aux
    4 langues. Ainsi un paragraphe n'est jamais rejeté parce qu'une traduction
    est légèrement plus courte que le seuil (l'allemand est structurellement
    plus compact que le français).
    """
    lines = {l: nonblank_lines(row.get(f"text_{l}", "")) for l in LANGS}
    counts_raw = {l: len(lines[l]) for l in LANGS}
    if len(set(counts_raw.values())) != 1:
        return lines, counts_raw, False
    lo = (row.get("orginal_language") or "fr").strip() or "fr"
    if lo not in LANGS:
        lo = "fr"
    n = counts_raw["fr"]
    keep = []
    for i in range(n):
        ref = lines[lo][i]                      # critère : langue d'origine
        if len(ref) <= min_chars:
            continue
        if fragment_guard and FRAGMENT_START.match(ref):
            continue
        keep.append(i)
    paras = {l: [lines[l][i] for i in keep] for l in LANGS}
    return paras, {l: len(paras[l]) for l in LANGS}, True


def divergence(lines, counts):
    mx = max(LANGS, key=lambda l: counts[l])
    mn = min(LANGS, key=lambda l: counts[l])
    i = counts[mn]
    sample = lines[mx][i][:100] if i < counts[mx] else ""
    return mx, mn, i, sample


def build_out_rows(row, paras, count, fields):
    base = (row.get("prompt_id") or "").strip()
    tcols = task_cols(fields)
    out = []
    for i in range(count):
        r = {c: "" for c in fields}
        r["prompt_id"] = f"{base}_p{i + 1:02d}"
        for m in META:
            r[m] = row.get(m, "")
        for c in tcols:
            r[c] = row.get(c, "")
        for l in LANGS:
            r[f"text_{l}"] = paras[l][i]
        out.append(r)
    return out


def write_csv(out_path, rows, fields):
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def run_all(args):
    fields, rows = load_rows(args.csv)
    exclude = {x.strip() for x in (args.exclude or "").split(",") if x.strip()}

    aligned_rows, misaligned = [], []
    for row in rows:
        pid = (row.get("prompt_id") or "").strip()
        paras, counts, ok = analyze(row, args.min_chars, not args.no_fragment_guard)
        if ok:
            aligned_rows.append((row, paras, counts["fr"]))
        else:
            misaligned.append((pid, paras, counts))

    print(f"=== {len(rows)} arrêts | alignés : {len(aligned_rows)} | "
          f"désalignés (exclus) : {len(misaligned)} ===")
    for pid, lines, counts in misaligned:
        mx, mn, i, sample = divergence(lines, counts)
        print(f"  {pid}: " + ", ".join(f"{l}={counts[l]}" for l in LANGS)
              + f" — décroche à la ligne {i + 1} (présent '{mx}', absent '{mn}')")
        if sample:
            print(f"      [{mx}] {sample!r}")

    combined = []
    skipped_excl = []
    for row, paras, count in aligned_rows:
        pid = (row.get("prompt_id") or "").strip()
        if pid in exclude:
            skipped_excl.append(pid)
            continue
        combined.extend(build_out_rows(row, paras, count, fields))

    n_arrets = len(aligned_rows) - len(skipped_excl)
    print(f"\narrêts inclus : {n_arrets} | exclus via --exclude : {skipped_excl or 'aucun'}")
    print(f"paragraphes au total : {len(combined)} "
          f"(moyenne {len(combined) / max(n_arrets, 1):.1f}/arrêt)")
    print(f"colonnes task recopiées : {task_cols(fields)}")

    out_path = Path(args.out_dir) / (args.out or "bger_para_200.csv")
    if not args.write:
        print(f"\n(Aperçu seulement — RIEN écrit.) Pour écrire : --write  ->  {out_path}")
        return
    write_csv(out_path, combined, fields)
    print(f"\n[OK] écrit : {out_path} ({len(combined)} lignes, {n_arrets} arrêts)")


def run_single(args):
    fields, rows = load_rows(args.csv)
    row = next((r for r in rows
                if (r.get("prompt_id") or "").strip() == args.prompt_id), None)
    if row is None:
        sys.exit(f"[STOP] prompt_id '{args.prompt_id}' introuvable dans {args.csv}")
    paras, counts, ok = analyze(row, args.min_chars, not args.no_fragment_guard)
    print(f"{args.prompt_id} — comptes : " + ", ".join(f"{l}={counts[l]}" for l in LANGS))
    if not ok:
        mx, mn, i, sample = divergence(paras, counts)
        print(f"[STOP] désaligné — décroche à la ligne {i + 1} "
              f"(présent '{mx}', absent '{mn}') : {sample!r}")
        sys.exit(1)
    for i in range(counts["fr"]):
        print(f"  p{i + 1:02d}: " + " | ".join(f"{l}={len(paras[l][i])}c" for l in LANGS))
    out_path = Path(args.out_dir) / f"bger_para_{args.prompt_id}.csv"
    if not args.write:
        print(f"(Aperçu seulement.) Pour écrire : --write -> {out_path}")
        return
    write_csv(out_path, build_out_rows(row, paras, counts["fr"], fields), fields)
    print(f"[OK] écrit : {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Découpe des arrêts en paragraphes (format canonique)")
    ap.add_argument("--prompt-id")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--exclude", default="", help="ids à exclure, séparés par des virgules")
    ap.add_argument("--csv", default="data/bger_dataset.csv")
    ap.add_argument("--out-dir", default="data")
    ap.add_argument("--out", default="", help="(--all) nom du fichier (défaut bger_para_200.csv)")
    ap.add_argument("--min-chars", type=int, default=MIN_PARA_CHARS,
                    help=f"longueur minimale du paragraphe dans la LANGUE D'ORIGINE (défaut {MIN_PARA_CHARS})")
    ap.add_argument("--no-fragment-guard", action="store_true",
                    help="désactive l'exclusion des lignes commençant en minuscule/ponctuation")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if args.all == bool(args.prompt_id):
        sys.exit("[STOP] choisis EXACTEMENT un mode : --prompt-id <id> OU --all")
    (run_all if args.all else run_single)(args)


if __name__ == "__main__":
    main()
