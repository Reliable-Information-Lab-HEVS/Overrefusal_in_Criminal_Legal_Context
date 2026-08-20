#!/usr/bin/env python3
"""Collect Swiss Federal Supreme Court (BGer) criminal judgments.

Queries the public AZA collection of bger.ch with offense-specific terms in
French and German, keeps criminal-law dockets only, extracts the *facts* section
in full (Sachverhalt / Faits / Fatti), and deduplicates by case reference and by
content. Article numbers are deliberately not used as queries: the same number
denotes unrelated provisions in different Swiss statutes.

Output is one row per judgment in the format of data/bger_sample.csv, with the
text in its original language only; run helpers/bger_translate.py afterwards to
fill the other language columns.

  python helpers/bger_scrape.py --out data/bger_full200.csv --target 180
  python helpers/bger_translate.py --in data/bger_full200.csv --out data/bger_full200.csv
"""
import argparse
import csv
import re
import time
from collections import Counter

import requests
from bs4 import BeautifulSoup

BASE = "https://www.bger.ch/ext/eurospider/live/fr/php"
HEADERS = {"User-Agent": "Mozilla/5.0 (academic research; BGer case-law collection)"}
SLEEP = 1.5   # be polite: about one request every 1.5 s

FIELDS = ["prompt_id", "or_category", "bger_source", "bger_url",
          "task_fr", "task_hard_fr", "task_de", "task_hard_de",
          "task_it", "task_hard_it", "task_en", "task_hard_en",
          "orginal_language", "text_fr", "text_de", "text_it", "text_en"]

# Search terms per category, French and German, unambiguous across statutes.
QUERIES = {
    "sexual": [
        '"contrainte sexuelle"', '"sexuelle Nötigung"', "Vergewaltigung",
        '"actes d\'ordre sexuel"', '"sexuelle Handlungen mit Kindern"',
        "pornographie", "Pornografie",
    ],
    "violence": [
        "assassinat", "Mord", "meurtre", '"vorsätzliche Tötung"',
        '"lésions corporelles graves"', '"schwere Körperverletzung"',
        "brigandage", "Raub",
    ],
    "self-harm": [
        '"assistance au suicide"', '"Beihilfe zum Selbstmord"',
        '"incitation au suicide"', '"Verleitung zum Selbstmord"',
        '"aide au suicide"', "Sterbehilfe",
    ],
    "illegal": [
        '"trafic de stupéfiants"', '"Betäubungsmittelhandel"', "Drogenhandel",
        '"blanchiment d\'argent"', '"Geldwäscherei"',
        '"organisation criminelle"', '"kriminelle Organisation"',
    ],
}

# A judgment is kept only if its facts section actually mentions the offense:
# this rejects hits where the term appears in an unrelated part of the page.
VERIFY = {
    "sexual": re.compile(
        r"contrainte sexuelle|sexuelle[rn]? Nötigung|coazione sessuale|\bviol\b|"
        r"Vergewaltigung|violenza carnale|acte[s]? d.ordre sexuel|sexuelle[rn]? Handlung|"
        r"atti sessuali|pornographie|Pornografie|pornografia", re.I),
    "violence": re.compile(
        r"assassinat|assassinio|\bMord|Mörder|meurtre|omicidio|Tötung|"
        r"lésions corporelles|Körperverletzung|lesioni.* gravi|brigandage|\bRaub|rapina",
        re.I),
    "self-harm": re.compile(
        r"\bsuicide\b|Selbstmord|Suizid|suicidio|Sterbehilfe|aide au suicide|"
        r"assistance au suicide|Beihilfe zum Selbstmord|Verleitung zum Selbstmord", re.I),
    "illegal": re.compile(
        r"stupéfiants|Betäubungsmittel|stupefacenti|\bLStup\b|\bBetmG\b|"
        r"blanchiment|Geldwäscherei|riciclaggio|organisation criminelle|"
        r"kriminelle[rn]? Organisation|Drogenhandel|trafic de drogue", re.I),
}

PENAL_DOCKET = ("6B_", "6S", "7B_", "6P")
FACTS_START = re.compile(r'(?:^|\n)\s*(Sachverhalt|Faits|Fatti)\s*:?\s*\n')
# Section ends, modern and older judgment layouts alike.
FACTS_END = (re.compile(r'\n\s*Erwägungen'), re.compile(r'\n\s*Considérant'),
             re.compile(r'\n\s*Diritto'),
             re.compile(r'\n[^\n]*zieht in Erwägung'),
             re.compile(r'\n[^\n]*considère en droit', re.I),
             re.compile(r'\n[^\n]*considerando in diritto', re.I),
             re.compile(r'\n\s*Par ces motifs', re.I),
             re.compile(r'\n\s*Demnach erkennt'))
NAV_CUT = re.compile(r'\n\s*navigation\s*\n|Nouvelle recherche')
LANG_HINT = [(re.compile(r'\bSachverhalt\b|\bUrteil vom\b'), "de"),
             (re.compile(r'\bFaits\b|\bArrêt du\b'), "fr"),
             (re.compile(r'\bFatti\b|\bSentenza\b'), "it")]


def q_enc(query):
    """Spaces to '+', accents in ISO-8859-1: the encoding the engine expects."""
    return requests.utils.quote(query.encode("latin-1"), safe="").replace("%20", "+")


def get(url):
    """Fetch and decode. Never trust the declared charset: bger.ch sometimes
    announces the wrong one, which mangles accented characters."""
    time.sleep(SLEEP)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    try:
        return r.content.decode("utf-8")
    except UnicodeDecodeError:
        return r.content.decode("iso-8859-1")


def page_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header"]):
        tag.decompose()
    return re.sub(r'\n{3,}', '\n\n', soup.get_text('\n'))


def search(query, max_pages=15):
    """Paginated AZA search -> ordered list of docids (aza://...)."""
    docids = []
    for page in range(1, max_pages + 1):
        url = (f"{BASE}/aza/http/index.php?lang=fr&type=simple_query"
               f"&query_words={q_enc(query)}&top_subcollection_aza=all"
               f"&from_date=&to_date=&page={page}&x=0&y=0")
        soup = BeautifulSoup(get(url), "html.parser")
        found = []
        for a in soup.find_all("a", href=True):
            m = re.search(r'highlight_docid=(aza[^&]+)', a["href"])
            if m:
                docid = requests.utils.unquote(m.group(1))
                if docid not in docids and docid not in found:
                    found.append(docid)
        if not found:
            break
        docids += found
    return docids


def doc_url(docid):
    return (f"{BASE}/aza/http/index.php?lang=fr&type=show_document"
            f"&highlight_docid={requests.utils.quote(docid, safe='')}")


def fetch_facts(docid):
    """Return (language, full facts section); the text is '' if there is none."""
    text = page_text(get(doc_url(docid))).replace('\xa0', ' ')
    start = FACTS_START.search(text)
    if not start:
        return "?", ""
    begin = start.end()
    ends = [rx.search(text).start() for rx in FACTS_END
            if rx.search(text) and rx.search(text).start() > begin]
    facts = text[begin:(min(ends) if ends else len(text))]
    cut = NAV_CUT.search(facts)      # drop any leftover page navigation
    if cut:
        facts = facts[:cut.start()]
    lang = next((l for rx, l in LANG_HINT if rx.search(text)), "?")
    return lang, tidy(facts)


def tidy(text):
    """Normalize paragraph breaks: strip trailing spaces, drop blank-only lines,
    and collapse runs of empty lines to a single one."""
    out = []
    for line in text.split("\n"):
        line = line.rstrip()
        if line == "" and (not out or out[-1] == ""):
            continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def canon_ref(docid):
    """aza://12-09-2018-6B_744-2018 -> 6B_744/2018;
    older dockets ...-6S-463-2005 -> 6S.463/2005 (dotted notation)."""
    core = docid.split("://")[1]
    m = re.search(r'\d{2}-\d{2}-\d{4}-(.+)$', core)
    ref = re.sub(r'-(\d{4})$', r'/\1', m.group(1) if m else core)
    m2 = re.match(r'^(\d?[A-Z]+)-(\d+/\d{4})$', ref)
    return f"{m2.group(1)}.{m2.group(2)}" if m2 else ref


def signature(text):
    """Content fingerprint, to catch the same case published under two refs."""
    return re.sub(r'\W+', '', text.lower())[:160]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/bger_full200.csv")
    ap.add_argument("--seed", default="data/bger_sample.csv",
                    help="existing judgments to keep and deduplicate against")
    ap.add_argument("--target", type=int, default=180, help="new judgments to collect")
    ap.add_argument("--per-category",
                    help='e.g. "sexual=60,violence=55,illegal=50,self-harm=15"')
    ap.add_argument("--min-facts", type=int, default=1000)
    ap.add_argument("--max-facts", type=int, default=20000)
    args = ap.parse_args()

    quotas = {"sexual": 60, "violence": 55, "illegal": 50, "self-harm": 15}
    for item in (args.per_category or "").split(","):
        if item.strip():
            key, value = item.split("=")
            quotas[key.strip()] = int(value)

    seed = list(csv.DictReader(open(args.seed, newline="", encoding="utf-8")))
    if not seed:
        raise SystemExit("--seed must point to a CSV holding the task columns "
                         "(data/bger_sample.csv)")
    tasks = {c: seed[0][c] for c in FIELDS if c.startswith("task")}

    seen_refs = {r["bger_source"].strip() for r in seed}
    seen_sigs = {signature(r["text_fr"] or r["text_de"]) for r in seed}
    new_rows, provenance, cache = [], [], {}

    def collect(category, need):
        """Add up to `need` judgments for a category; return how many were added."""
        added = 0
        for query in QUERIES[category]:
            if added >= need:
                break
            if query not in cache:
                try:
                    cache[query] = search(query)
                    print(f"[i] {category:9s} | {query!r}: {len(cache[query])} candidates")
                except Exception as exc:
                    print(f"[!] search {query!r}: {exc}")
                    cache[query] = []
            for docid in cache[query]:
                if added >= need:
                    break
                ref = canon_ref(docid)
                if ref in seen_refs or not ref.startswith(PENAL_DOCKET):
                    continue
                try:
                    lang, facts = fetch_facts(docid)
                except Exception:
                    continue
                if not (args.min_facts <= len(facts) <= args.max_facts):
                    continue
                if not VERIFY[category].search(facts):
                    continue
                sig = signature(facts)
                if sig in seen_sigs:
                    continue
                seen_refs.add(ref)
                seen_sigs.add(sig)
                row = {k: "" for k in FIELDS}
                row.update({"or_category": category, "bger_source": ref,
                            "bger_url": doc_url(docid), "orginal_language": lang,
                            f"text_{lang}": facts, **tasks})
                new_rows.append(row)
                provenance.append({"bger_source": ref, "or_category": category,
                                   "query": query, "language": lang,
                                   "facts_chars": len(facts)})
                added += 1
                print(f"    + [{category}] {ref} ({lang}, {len(facts)} chars) "
                      f"[{added}/{need}]")
        return added

    for category in QUERIES:                       # pass 1: per-category quota
        collect(category, quotas.get(category, 0))

    exhausted = set()                              # pass 2: top up to --target
    while len(new_rows) < args.target and len(exhausted) < len(QUERIES):
        for category in QUERIES:
            if len(new_rows) >= args.target or category in exhausted:
                continue
            if collect(category, min(5, args.target - len(new_rows))) == 0:
                exhausted.add(category)
    if len(new_rows) < args.target:
        print(f"[!] target {args.target} not reached: "
              f"{len(new_rows)} judgments collected")

    for i, row in enumerate(new_rows, start=len(seed) + 1):
        row["prompt_id"] = f"bgr_{i:03d}"
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(seed + new_rows)

    prov_path = args.out.replace(".csv", "_provenance.csv")
    with open(prov_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, lineterminator="\n",
                           fieldnames=["bger_source", "or_category", "query",
                                       "language", "facts_chars"])
        w.writeheader()
        w.writerows(provenance)

    print(f"\n[ok] {len(seed) + len(new_rows)} judgments -> {args.out} "
          f"({len(seed)} seed + {len(new_rows)} new)")
    print(f"[ok] provenance -> {prov_path}")
    print(f"[i] per category: {dict(Counter(p['or_category'] for p in provenance))} | "
          f"source language: {dict(Counter(p['language'] for p in provenance))}")
    print(f"    Next: python helpers/bger_translate.py --in {args.out} --out {args.out}")


if __name__ == "__main__":
    main()
