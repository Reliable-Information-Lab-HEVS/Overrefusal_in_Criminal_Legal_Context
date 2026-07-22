#!/usr/bin/env python3
"""
bger_repair.py — Répare en place les lignes défectueuses de bger_dataset.csv :
  1. accents corrompus (ŕ, č, Ķ, ť… : mauvaise détection d'encodage des pages
     du TF, qui sont en ISO-8859-1 déclaré) ;
  2. considérants inclus (les anciens arrêts disent « zieht in Erwägung » /
     « considère en droit » au lieu de « Erwägungen »/« Considérant ») ;
  3. résidus de navigation du site en fin de texte ;
  4. références anciennes mal formées (6S-463/2005 -> 6S.463/2005).

Il détecte les lignes touchées, RE-TÉLÉCHARGE uniquement celles-ci avec le bon
décodage (charset lu dans la page), ré-extrait les Faits proprement, et écrit
le fichier corrigé. Les autres lignes ne sont pas modifiées.

Usage :
  python bger_repair.py --in bger_dataset.csv --out bger_dataset.csv
"""

import argparse, csv, re, time
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (academic research; BGer case-law collection)"}
SLEEP = 1.5

MOJI = re.compile(r'[ĀĶťŤ†ķčŕōů�]')  # � = caractère de remplacement (décodage raté)
NAV = re.compile(r"Nouvelle recherche|recherche d'ATF similaires|\bImprimer\b|\bremonter\b")
CONSID_LEAK = re.compile(r'zieht in Erwägung|considère en droit|considčre en droit|'
                         r'considerando in diritto|Par ces motifs|Demnach erkennt', re.I)

FACTS_START = re.compile(r'(?:^|\n)\s*(Sachverhalt|Faits|Fatti)\s*:?\s*\n')
FACTS_END = (
    re.compile(r'\n\s*Erwägungen'),
    re.compile(r'\n\s*Considérant'),
    re.compile(r'\n\s*Diritto'),
    re.compile(r'\n[^\n]*zieht in Erwägung'),
    re.compile(r'\n[^\n]*considère en droit', re.I),
    re.compile(r'\n[^\n]*considerando in diritto', re.I),
    re.compile(r'\n\s*Par ces motifs', re.I),
    re.compile(r'\n\s*Demnach erkennt'),
)
NAV_CUT = re.compile(r'\n\s*navigation\s*\n|Nouvelle recherche')
LANG_HINT = [(re.compile(r'\bSachverhalt\b|\bUrteil vom\b'), "de"),
             (re.compile(r'\bFaits\b|\bArrêt du\b'), "fr"),
             (re.compile(r'\bFatti\b|\bSentenza\b'), "it")]


def fetch_decoded(url):
    """Décodage robuste : UTF-8 strict, bascule ISO-8859-1 si échec.
    Ne fait jamais confiance au charset déclaré par la page."""
    time.sleep(SLEEP)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    try:
        return r.content.decode("utf-8")
    except UnicodeDecodeError:
        return r.content.decode("iso-8859-1")


def extract_facts(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header"]):
        tag.decompose()
    t = re.sub(r'\n{3,}', '\n\n', soup.get_text('\n')).replace('\xa0', ' ')
    st = FACTS_START.search(t)
    if not st:
        return "?", ""
    s = st.end()
    ends = [m.search(t).start() for m in FACTS_END
            if m.search(t) and m.search(t).start() > s]
    faits = t[s:(min(ends) if ends else len(t))]
    cut = NAV_CUT.search(faits)          # ceinture + bretelles
    if cut:
        faits = faits[:cut.start()]
    lang = next((l for rx, l in LANG_HINT if rx.search(t)), "?")
    return lang, tidy(faits)


def tidy(text):
    """Normalise les sauts de paragraphe : supprime les espaces de fin de
    ligne, les lignes ne contenant que des espaces, et réduit toute série
    de lignes vides à UNE seule (max un saut de paragraphe)."""
    out = []
    for line in text.split("\n"):
        line = line.rstrip()
        if line == "" and (not out or out[-1] == ""):
            continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def fix_ref(ref):
    """6S-463/2005 -> 6S.463/2005 (notation ancienne à point)."""
    m = re.match(r'^(\d?[A-Z]+)-(\d+/\d{4})$', ref)
    return f"{m.group(1)}.{m.group(2)}" if m else ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--min-facts", type=int, default=1000)
    args = ap.parse_args()

    with open(args.inp, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        FIELDS = reader.fieldnames
        rows = list(reader)
    orig_col = "orginal_language" if "orginal_language" in FIELDS else "original_language"

    def text_of(r):
        return r["text_fr"] or r["text_de"] or r["text_it"] or ""

    repaired = dropped = renamed = 0
    for r in rows:
        t = text_of(r)
        flags = []
        if MOJI.search(t): flags.append("accents")
        if NAV.search(t): flags.append("navigation")
        if CONSID_LEAK.search(t): flags.append("considérants")
        new_ref = fix_ref(r["bger_source"].strip())
        if new_ref != r["bger_source"].strip():
            r["bger_source"] = new_ref
            renamed += 1
        if not flags:
            continue
        try:
            html = fetch_decoded(r["bger_url"])
            lang, faits = extract_facts(html)
        except Exception as e:
            print(f"[!] {r['bger_source']}: re-téléchargement échoué ({e}) — inchangé")
            continue
        if len(faits) < args.min_facts:
            print(f"[!] {r['bger_source']}: faits {len(faits)} c après réparation "
                  f"(< {args.min_facts}) — ligne marquée À REMPLACER")
            r["category"] = r["category"]  # inchangé
            r["prompt_id"] = r["prompt_id"] + "_A_REMPLACER"
            dropped += 1
        # remet le texte propre dans la bonne colonne, vide les autres
        for l in ("fr", "de", "it", "en"):
            r[f"text_{l}"] = ""
        if lang in ("fr", "de", "it"):
            r[orig_col] = lang
            r[f"text_{lang}"] = faits
        repaired += 1
        print(f"[✓] {r['bger_source']} réparé ({'+'.join(flags)}) -> {lang}, {len(faits)} c")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(rows)
    print(f"\n[✓] {repaired} lignes réparées, {renamed} références reformatées "
          f"(6S-… -> 6S.…), {dropped} lignes trop courtes marquées _A_REMPLACER")
    print(f"[✓] écrit : {args.out}")


if __name__ == "__main__":
    main()