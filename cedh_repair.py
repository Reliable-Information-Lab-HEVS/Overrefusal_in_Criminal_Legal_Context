#!/usr/bin/env python3
"""
cedh_repair.py — Répare EN PLACE les textes du dataset CEDH déjà collecté,
sans re-téléchargement (transformation de texte pure) :

  1. COUPE le cadre légal inclus à tort (« RELEVANT DOMESTIC LAW »,
     « RELEVANT LEGAL FRAMEWORK AND PRACTICE », « LE DROIT INTERNE
     PERTINENT »…) — l'équivalent CEDH de la fuite de considérants BGer ;
  2. DÉMARRE aux circonstances de l'espèce quand la sous-section existe
     (« THE CIRCUMSTANCES OF THE CASE » / « LES CIRCONSTANCES DE L'ESPÈCE ») ;
  3. RECONSTRUIT une ligne par paragraphe numéroté CEDH : les numéros
     éclatés (« 5. » seul sur sa ligne, voire « 5 » puis « . ») sont recollés
     au texte, les phrases cassées par la mise en page HUDOC (« 10\n\nMay
     2010 », « inter alia » isolé) sont recousues. L'unité redevient le
     paragraphe officiel de l'arrêt — le miroir des lettres A./B.a du BGer.

Usage :
  python cedh_repair.py --in data/cedh_dataset.csv --out data/cedh_dataset.csv
  # option : --min-facts 1000  (marque _A_VERIFIER si le texte réparé est trop court)
"""

import argparse
import csv
import re

csv.field_size_limit(10**8)

# --- fin des faits : cadre légal / droit interne (EN + FR, variantes) --------
END_MARKERS = re.compile(
    r"RELEVANT (DOMESTIC|LEGAL|INTERNATIONAL|COUNCIL OF EUROPE)[A-Z ,'’\-]*|"
    r"RELEVANT DOMESTIC AND INTERNATIONAL[A-Z ,'’\-]*|"
    r"LE DROIT (INTERNE|ET LA PRATIQUE)[A-ZÉÈ ,'’\-]*|"
    r"DROIT INTERNE PERTINENT|LE CADRE JURIDIQUE[A-ZÉÈ ,'’\-]*|"
    r"TEXTES? (INTERNES? )?PERTINENTS?|"
    r"\bTHE LAW\b|\bEN DROIT\b|FOR THESE REASONS|PAR CES MOTIFS"
)
# --- début préféré : circonstances de l'espèce -------------------------------
CIRC = re.compile(r"THE CIRCUMSTANCES OF THE CASE|LES CIRCONSTANCES DE L['’]ESP[ÈE]CE")

TITLE = re.compile(r"^([IVXLC]+\.?|[A-Z]\.|[A-Z][A-Z '’&,\-]{3,})$")
NUM = re.compile(r"^(\d{1,3})\s*\.?\s*$")
DOT = re.compile(r"^\.\s*$")
# ligne « N. texte » (numéro et texte sur la MÊME ligne) : nouveau paragraphe
NUM_INLINE = re.compile(r"^(\d{1,3})\.\s+\S")
# titre alphabétique de sous-sous-section « (a) … »
ALPHA_HEAD = re.compile(r"^\([a-z]\)\s+\S")
# titre de sous-section collé en FIN de ligne après une fin de phrase :
# « …Prison. 1. Proceedings leading to the applicant's conviction »
GLUED_HEAD = re.compile(r"[.!?»”]\s+((?:\d{1,2}\.|\([a-z]\))\s+[^.!?]{5,250})$")
# scinde « 2. Titre … (a) Sous-titre » en deux
SPLIT_ALPHA = re.compile(r"^((?:\d{1,2}\.)\s+[^(]{5,220}?)\s+(\([a-z]\)\s+.*)$")


def detach_glued_headings(text):
    """Détache les titres de sous-sections collés en fin de ligne."""
    out = []
    for line in text.split("\n"):
        stack = [line]
        while True:
            m = GLUED_HEAD.search(stack[-1])
            if not m:
                break
            head = m.group(1).strip()
            stack[-1] = stack[-1][:m.start(1)].rstrip()
            stack.append(head)
        # scinde les doubles titres « N. Titre (a) Sous-titre »
        final = []
        for l in stack:
            m2 = SPLIT_ALPHA.match(l)
            if m2:
                final.extend([m2.group(1).strip(), m2.group(2).strip()])
            else:
                final.append(l)
        out.extend(final)
    return "\n".join(out)


def cut_sections(text):
    """Garde des circonstances de l'espèce jusqu'au premier marqueur de droit."""
    m = CIRC.search(text)
    if m:
        text = text[m.end():]
    e = END_MARKERS.search(text)
    if e:
        text = text[:e.start()]
    return text


def normalize_paragraphs(text):
    """Une ligne par paragraphe numéroté ; titres sur lignes à part."""
    lines = [l.strip() for l in text.split("\n")]
    out, cur = [], ""

    def flush():
        nonlocal cur
        if cur.strip():
            out.append(re.sub(r"\s+", " ", cur).strip())
        cur = ""

    i = 0
    while i < len(lines):
        s = lines[i]
        if not s:
            i += 1
            continue
        m = NUM.match(s)
        if m:
            flush()
            cur = m.group(1) + ". "
            j = i + 1
            while j < len(lines) and not lines[j]:
                j += 1
            if j < len(lines) and DOT.match(lines[j]):
                i = j
        elif NUM_INLINE.match(s):        # « N. texte » sur une seule ligne
            flush()
            cur = s
        elif ALPHA_HEAD.match(s):        # « (a) … » : titre, ligne à part
            flush()
            out.append(s)
        elif TITLE.match(s):
            flush()
            out.append(s)
        else:
            cur += (" " if cur else "") + s
        i += 1
    flush()
    # purge les titres/numéros orphelins en fin de texte (ex. « II. » du
    # cadre légal qui suit)
    while out and (TITLE.match(out[-1]) or NUM.match(out[-1])):
        out.pop()
    return "\n".join(out)


def repair(text):
    if not (text or "").strip():
        return text
    return normalize_paragraphs(detach_glued_headings(cut_sections(text)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--min-facts", type=int, default=1000)
    args = ap.parse_args()

    with open(args.inp, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames
        rows = list(rd)

    fixed = short = 0
    for r in rows:
        for col in ("text_en", "text_fr", "text_de", "text_it"):
            t = r.get(col) or ""
            if not t.strip():
                continue
            nt = repair(t)
            if nt != t:
                r[col] = nt
                fixed += 1
        lo = "text_" + ((r.get("orginal_language") or "en").strip() or "en")
        if (r.get(lo) or "") and len(r[lo]) < args.min_facts:
            if "_A_VERIFIER" not in r["prompt_id"]:
                r["prompt_id"] += "_A_VERIFIER"
            short += 1
            print(f"[!] {r['prompt_id']}: {len(r[lo])} c après réparation (court)")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\n[✓] {fixed} cellules réparées (droit interne coupé + paragraphes reconstruits)")
    print(f"[i] lignes trop courtes marquées _A_VERIFIER : {short}")
    print(f"[✓] écrit : {args.out}")


if __name__ == "__main__":
    main()
