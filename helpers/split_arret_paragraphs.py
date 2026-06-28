#!/usr/bin/env python3
"""Split BGer arrêts into paragraphs, one CSV row per paragraph.

Rule: inside each text_{lang}, split on newlines (\n). A line whose stripped
content is > 25 characters is a paragraph; lines <= 25 chars (e.g. "A.",
"B.c", blank lines) are dropped. The stored paragraph is the stripped line.

Two modes, both PREVIEW-ONLY by default (nothing written without --write):

  Single arrêt:
    python helpers/split_arret_paragraphs.py --prompt-id bgr_02            # preview
    python helpers/split_arret_paragraphs.py --prompt-id bgr_02 --write    # -> data/bger_para_bgr_02.csv

  All arrêts into one file:
    python helpers/split_arret_paragraphs.py --all                         # recap preview
    python helpers/split_arret_paragraphs.py --all --write                 # -> data/bger_para_ALL.csv
    python helpers/split_arret_paragraphs.py --all --exclude bgr_14 --write # skip given ids

In --all mode, only arrêts whose 4 languages have the SAME paragraph count
are concatenated; misaligned arrêts are listed (with the divergence point)
and skipped. Output keeps the same columns/format as bger_sample.csv, with
prompt_id = "<source_id>_p01", "<source_id>_p02", ...
"""

import argparse
import csv
import sys
from pathlib import Path

LANGS = ["fr", "de", "it", "en"]
MIN_PARA_CHARS = 30

# Output columns = EXACTLY bger_sample.csv, same order.
COLUMNS = [
    "prompt_id", "or_category", "bger_source", "bger_url",
    "task_fr", "task_hard_fr", "task_de", "task_hard_de",
    "task_it", "task_hard_it", "task_en", "task_hard_en",
    "orginal_language", "text_fr", "text_de", "text_it", "text_en",
]


def split_paragraphs(text):
    """Return paragraphs (stripped lines whose stripped length > 25), in order."""
    out = []
    for line in (text or "").split("\n"):
        s = line.strip()
        if len(s) > MIN_PARA_CHARS:
            out.append(s)
    return out


def load_rows(csv_path):
    """All rows, in file order. newline='' keeps embedded field newlines intact."""
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def nonblank_lines(text):
    return [s for s in (l.strip() for l in (text or "").split("\n")) if s]

def analyze(row):
    lines = {lang: nonblank_lines(row.get(f"text_{lang}", "")) for lang in LANGS}
    counts_raw = {lang: len(lines[lang]) for lang in LANGS}
    # garde-fou: mêmes lignes brutes, sinon désync RÉELLE au niveau ligne
    if len(set(counts_raw.values())) != 1:
        return None, counts_raw, False
    n = next(iter(counts_raw.values()))
    keep = [i for i in range(n)
            if min(len(lines[l][i]) for l in LANGS) > MIN_PARA_CHARS]
    paras = {lang: [lines[lang][i] for i in keep] for lang in LANGS}
    counts = {lang: len(paras[lang]) for lang in LANGS}
    return paras, counts, True   # aligné par construction


def divergence(paras, counts):
    """Where alignment breaks: (lang_max, lang_min, first_missing_idx, sample)."""
    mx = max(LANGS, key=lambda l: counts[l])
    mn = min(LANGS, key=lambda l: counts[l])
    i = counts[mn]
    sample = paras[mx][i][:100] if i < counts[mx] else ""
    return mx, mn, i, sample


def build_out_rows(row, paras, count):
    """Build the per-paragraph output dicts for one aligned arrêt."""
    base = (row.get("prompt_id") or "").strip()   # keep underscore: bgr_02 -> bgr_02_p01
    out = []
    for i in range(count):
        r = {c: "" for c in COLUMNS}              # task_hard_* stay empty
        r["prompt_id"] = f"{base}_p{i+1:02d}"
        for meta in ("or_category", "bger_source", "bger_url", "orginal_language"):
            r[meta] = row.get(meta, "")
        for lang in LANGS:
            r[f"task_{lang}"] = row.get(f"task_{lang}", "")
            r[f"text_{lang}"] = paras[lang][i]
        out.append(r)
    return out


def write_csv(out_path, rows):
    """Write rows in bger_sample.csv format (LF line endings, UTF-8, no BOM)."""
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def preview_rows(rows, n=3):
    """Print the first n output rows, key columns only, text truncated."""
    show = ["prompt_id", "or_category", "bger_source", "bger_url",
            "task_fr", "task_hard_fr", "orginal_language",
            "text_fr", "text_de", "text_it", "text_en"]
    for r in rows[:n]:
        print("  " + "-" * 56)
        for c in show:
            v = r[c]
            disp = (v[:70] + "…") if len(v) > 70 else v
            print(f"    {c:16} = {disp!r}")


# ---------------------------------------------------------------------------
# Single-arrêt mode
# ---------------------------------------------------------------------------
def run_single(args):
    rows = {(r.get("prompt_id") or "").strip(): r for r in load_rows(args.csv)}
    row = rows.get(args.prompt_id)
    if row is None:
        sys.exit(f"[STOP] prompt_id '{args.prompt_id}' introuvable dans {args.csv}")

    paras, counts, aligned = analyze(row)
    n = max(counts.values()) if counts else 0

    print(f"\nArrêt: {args.prompt_id}   (source: {args.csv})")
    print(f"or_category={row.get('or_category','')!r}  "
          f"orginal_language={row.get('orginal_language','')!r}")
    print("\n  paragraphe | nb_car_fr | nb_car_de | nb_car_it | nb_car_en")
    print("  " + "-" * 58)
    for i in range(n):
        cells = [str(len(paras[l][i])) if i < counts[l] else "—" for l in LANGS]
        print("  " + f"p{i+1:02d}".ljust(11) + "| " +
              " | ".join(c.rjust(9) for c in cells))
    print("  " + "-" * 58)
    print("  " + "total".ljust(11) + "| " +
          " | ".join(str(counts[l]).rjust(9) for l in LANGS))

    if not aligned:
        mx, mn, i, sample = divergence(paras, counts)
        print("\n[STOP] Les 4 langues n'ont PAS le même nombre de paragraphes.")
        print("  Comptes : " + ", ".join(f"{l}={counts[l]}" for l in LANGS))
        print(f"  Divergence : '{mx}' a {counts[mx]} paragraphes, "
              f"'{mn}' en a {counts[mn]}.")
        if sample:
            print(f"\n  Décroche à p{i+1:02d} "
                  f"(présent dans '{mx}', absent dans '{mn}') :")
            print(f"    [{mx}] {sample!r}")
            print(f"    [{mn}] <ce paragraphe n'existe pas>")
        print("\nAucun fichier écrit.")
        sys.exit(1)

    count = counts["fr"]
    out_rows = build_out_rows(row, paras, count)
    out_path = Path(args.out_dir) / f"bger_para_{args.prompt_id}.csv"

    print(f"\nComptes ÉGAUX ({count} paragraphes). Aperçu des 3 premières lignes :")
    preview_rows(out_rows)

    if not args.write:
        print("\n(Aperçu seulement — RIEN écrit.) Pour écrire : ajoute --write")
        print(f"Cible : {out_path}")
        return

    write_csv(out_path, out_rows)
    print(f"\n[OK] Écrit : {out_path}  ({count} lignes)")


# ---------------------------------------------------------------------------
# All-arrêts mode
# ---------------------------------------------------------------------------
def run_all(args):
    rows = load_rows(args.csv)
    exclude = {x.strip() for x in (args.exclude or "").split(",") if x.strip()}

    print(f"\n=== RÉCAP split sur {len(rows)} arrêts (source: {args.csv}) ===")
    print("  prompt_id | fr | de | it | en | ALIGNÉ")
    print("  " + "-" * 44)

    aligned_rows, misaligned = [], []
    for row in rows:
        pid = (row.get("prompt_id") or "").strip()
        paras, counts, aligned = analyze(row)
        flag = "oui" if aligned else "NON"
        print("  " + pid.ljust(9) + "| " +
              " | ".join(str(counts[l]).rjust(2) for l in LANGS) +
              f" | {flag}")
        if aligned:
            aligned_rows.append((row, paras, counts["fr"]))
        else:
            misaligned.append((pid, paras, counts))
    print("  " + "-" * 44)

    # Misaligned report
    if misaligned:
        print(f"\n=== NON ALIGNÉS ({len(misaligned)}) — exclus du fichier ===")
        for pid, paras, counts in misaligned:
            mx, mn, i, sample = divergence(paras, counts)
            print(f"  {pid}: " + ", ".join(f"{l}={counts[l]}" for l in LANGS))
            print(f"     décroche à p{i+1:02d} (présent '{mx}', absent '{mn}')")
            if sample:
                print(f"       [{mx}] {sample!r}")
    else:
        print("\n=== NON ALIGNÉS : aucun ===")

    # Build combined rows from aligned, minus excluded
    skipped_excl = [
        (r.get("prompt_id") or "").strip()
        for r, _, _ in aligned_rows
        if (r.get("prompt_id") or "").strip() in exclude
    ]
    combined = []
    for row, paras, count in aligned_rows:
        pid = (row.get("prompt_id") or "").strip()
        if pid in exclude:
            continue
        combined.extend(build_out_rows(row, paras, count))

    included = sorted({r["prompt_id"].rsplit("_p", 1)[0] for r in combined})
    print(f"\n=== À ÉCRIRE ===")
    print(f"  arrêts alignés : {len(aligned_rows)} | exclus (--exclude) : "
          f"{skipped_excl or 'aucun'}")
    print(f"  arrêts inclus  : {len(included)} -> {included}")
    print(f"  lignes (paragraphes) au total : {len(combined)}")

    out_path = Path(args.out_dir) / (args.out or "bger_para_ALL.csv")
    print(f"\nAperçu des 3 premières lignes de {out_path} :")
    preview_rows(combined)

    if not args.write:
        print("\n(Aperçu seulement — RIEN écrit.) Pour écrire : ajoute --write")
        print(f"Cible : {out_path}")
        return

    write_csv(out_path, combined)
    print(f"\n[OK] Écrit : {out_path}  ({len(combined)} lignes, {len(included)} arrêts)")


def main():
    ap = argparse.ArgumentParser(description="Split BGer arrêt(s) into paragraph rows")
    ap.add_argument("--prompt-id", help="Single source prompt_id, e.g. bgr_02")
    ap.add_argument("--all", action="store_true",
                    help="Process every arrêt into one concatenated file")
    ap.add_argument("--exclude", default="",
                    help="(--all) comma-separated prompt_ids to skip, e.g. bgr_14")
    ap.add_argument("--csv", default="data/bger_sample.csv", help="Source CSV")
    ap.add_argument("--out-dir", default="data", help="Folder for the output CSV")
    ap.add_argument("--out", default="",
                    help="(--all) output filename (default: bger_para_ALL.csv)")
    ap.add_argument("--write", action="store_true",
                    help="Actually write the CSV (default: preview only, nothing written)")
    args = ap.parse_args()

    if args.all == bool(args.prompt_id):
        sys.exit("[STOP] choisis EXACTEMENT un mode : --prompt-id <id>  OU  --all")

    if args.all:
        run_all(args)
    else:
        run_single(args)


if __name__ == "__main__":
    main()
