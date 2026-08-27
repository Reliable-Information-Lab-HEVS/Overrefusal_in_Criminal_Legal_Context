#!/usr/bin/env python3
"""Split judgments into paragraphs, one CSV row per paragraph.

bgr_001 becomes bgr_001_p01, bgr_001_p02, ... The four language columns must
line up, so a judgment is kept only if its text has the same number of non-empty
lines in every language; the ones that do not are listed and excluded (8 of 200
judgments, leaving the 192 used in the paper).

Which lines to keep is decided once, on the judgment's own source language, and
that decision is applied to all four columns. Deciding per language would drop
paragraphs simply because German is more compact than French.

  python helpers/split_paragraphs.py --csv data/bger_full200.csv            # preview
  python helpers/split_paragraphs.py --csv data/bger_full200.csv --write
"""
import argparse
import csv
import sys
from pathlib import Path

csv.field_size_limit(10**8)

LANGS = ["fr", "de", "it", "en"]
MIN_PARA_CHARS = 100
META = ("or_category", "bger_source", "bger_url", "orginal_language")

# Fragment guard: a line starting with a lowercase letter or with continuation
# punctuation is a sentence cut by the page layout, not a paragraph.
import re
FRAGMENT_START = re.compile(r'^[a-zà-öø-ÿ]|^[,;:.)\]]|^\'|^"?\.\s')


def nonblank_lines(text):
    return [s for s in (line.strip() for line in (text or "").split("\n")) if s]


def analyze(row, min_chars, fragment_guard=True):
    """Return (paragraphs per language, counts, aligned?)."""
    lines = {l: nonblank_lines(row.get(f"text_{l}", "")) for l in LANGS}
    counts = {l: len(lines[l]) for l in LANGS}
    if len(set(counts.values())) != 1:
        return lines, counts, False

    source = (row.get("orginal_language") or "fr").strip()
    source = source if source in LANGS else "fr"
    keep = []
    for i in range(counts["fr"]):
        reference = lines[source][i]
        if len(reference) <= min_chars:
            continue
        if fragment_guard and FRAGMENT_START.match(reference):
            continue
        keep.append(i)
    paragraphs = {l: [lines[l][i] for i in keep] for l in LANGS}
    return paragraphs, {l: len(paragraphs[l]) for l in LANGS}, True


def divergence(lines, counts):
    """Where the languages stop matching, for the misalignment report."""
    longest = max(LANGS, key=lambda l: counts[l])
    shortest = min(LANGS, key=lambda l: counts[l])
    i = counts[shortest]
    sample = lines[longest][i][:100] if i < counts[longest] else ""
    return longest, shortest, i, sample


def build_rows(row, paragraphs, count, fields):
    base = (row.get("prompt_id") or "").strip()
    task_cols = [c for c in fields if c.startswith("task")]
    out = []
    for i in range(count):
        new = {c: "" for c in fields}
        new["prompt_id"] = f"{base}_p{i + 1:02d}"
        for col in META + tuple(task_cols):
            new[col] = row.get(col, "")
        for lang in LANGS:
            new[f"text_{lang}"] = paragraphs[lang][i]
        out.append(new)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/bger_full200.csv")
    ap.add_argument("--out", default="data/bger_para200.csv")
    ap.add_argument("--min-chars", type=int, default=MIN_PARA_CHARS,
                    help=f"minimum paragraph length in the SOURCE language "
                         f"(default {MIN_PARA_CHARS})")
    ap.add_argument("--no-fragment-guard", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    aligned, misaligned = [], []
    for row in rows:
        paragraphs, counts, ok = analyze(row, args.min_chars, not args.no_fragment_guard)
        if ok:
            aligned.append((row, paragraphs, counts["fr"]))
        else:
            misaligned.append(((row.get("prompt_id") or "").strip(), paragraphs, counts))

    print(f"=== {len(rows)} judgments | aligned: {len(aligned)} | "
          f"excluded: {len(misaligned)} ===")
    for pid, lines, counts in misaligned:
        longest, shortest, i, sample = divergence(lines, counts)
        print(f"  {pid}: " + ", ".join(f"{l}={counts[l]}" for l in LANGS)
              + f" - diverges at line {i + 1} (in '{longest}', missing in '{shortest}')")
        if sample:
            print(f"      [{longest}] {sample!r}")

    out_rows = []
    for row, paragraphs, count in aligned:
        out_rows.extend(build_rows(row, paragraphs, count, fields))
    print(f"\nparagraphs: {len(out_rows)} "
          f"(mean {len(out_rows) / max(len(aligned), 1):.1f} per judgment)")

    if not args.write:
        print(f"(preview only, nothing written; add --write -> {args.out})")
        return
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)
    print(f"[ok] wrote {args.out} ({len(out_rows)} rows, {len(aligned)} judgments)")


if __name__ == "__main__":
    main()
