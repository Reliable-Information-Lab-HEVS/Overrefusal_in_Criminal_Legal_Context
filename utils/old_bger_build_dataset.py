#!/usr/bin/env python3
"""
bger_build_dataset.py — Dataset BGer construit À PARTIR DE ZÉRO sur la base
des DESCRIPTEURS OFFICIELS du BGer, au format EXACT des 20 arrêts d'origine.
 
Principe (2 étages) :
  1. SÉLECTION par le thésaurus officiel du BGer (« Descripteurs ATF dès 1990 »,
     recherche avancée abonnés, session edu-ID). Les listes d'ATF taggés par
     descripteur, restreintes à 2000+ (là où le texte intégral existe), ont été
     relevées le 22.07.2026 et sont GELÉES ci-dessous (SEEDS) — le script
     lui-même n'a donc PAS besoin du login.
  2. TEXTE INTÉGRAL : pour chaque ATF taggé, le script retrouve l'arrêt COMPLET
     correspondant (via son numéro de dossier) dans la collection publique AZA
     et en extrait la section Faits/Sachverhalt ENTIÈRE (jusqu'à
     Considérant/Erwägungen). Jamais l'extrait squelettique du recueil.
 
Vérifié le 22.07.2026 : le thésaurus n'indexe QUE les ATF (sur la collection
AZA, <DESCRIPTEUR> = recherche plein texte, même connecté). D'où ce montage.
 
Sortie : UN fichier neuf = tes 20 d'origine (intacts) + les nouveaux, mêmes
13 colonnes. Colonnes de traduction vides pour les nouveaux (bger_translate.py
ensuite). Un fichier de provenance à part trace descripteur → BGE → dossier.
 
Usage :
  pip install requests beautifulsoup4
  python bger_build_dataset.py --sample bger_sample.csv --out bger_dataset.csv
  # mode strict par défaut (~90-110 nouveaux, uniquement les taggés).
  # pour compléter jusqu'à un quota avec des requêtes plein texte sur les
  # termes officiels (provenance marquée) :
  #   --fill --per-category "sexual=55,violence=50,illegal=45,self-harm=10"
"""
 
import argparse, csv, re, sys, time
import requests
from bs4 import BeautifulSoup
 
BASE = "https://www.bger.ch/ext/eurospider/live/fr/php"
HEADERS = {"User-Agent": "Mozilla/5.0 (academic research; BGer case-law collection)"}
SLEEP = 1.5
 
# ============================================================================
# SEEDS — ATF 2000+ taggés par les DESCRIPTEURS OFFICIELS du BGer.
# Relevés le 22.07.2026 via la recherche avancée abonnés (session edu-ID),
# requêtes <DESCRIPTEUR>, azaclir=clir, from_year=2000. Références "vol-partie-page".
# ============================================================================
SEEDS = {
    "sexual": {
        "<CONTRAINTE SEXUELLE>": ["126-IV-121","127-IV-198","128-IV-106","128-IV-97",
            "131-IV-107","131-IV-167","132-IV-120","133-IV-49","141-IV-423",
            "146-IV-153","147-IV-409"],
        "<VIOL>": ["126-IV-124","126-IV-121","127-IV-86","128-IV-106","129-I-49",
            "131-IV-167","132-IV-120","147-IV-409"],
        "<ACTE D'ORDRE SEXUEL AVEC UN ENFANT>": ["127-IV-86","129-IV-168","131-IV-100",
            "134-IV-266","141-IV-93","143-IV-9","146-IV-153","149-IV-161"],
        "<PORNOGRAPHIE>": ["128-IV-25","128-IV-201","128-IV-260","129-III-604",
            "131-IV-16","131-IV-64","133-IV-31","133-II-136","137-IV-208",
            "144-II-233","149-IV-161","152-I-105","152-IV-176"],
    },
    "violence": {
        "<ASSASSINAT>": ["127-IV-10","127-IV-215","141-IV-61","144-IV-345"],
        "<MEURTRE>": ["127-IV-10","130-IV-58","133-IV-1","133-IV-9","133-IV-58",
            "133-IV-76","137-IV-113","141-IV-61","143-I-292","143-IV-330","150-IV-149"],
        "<LÉSION CORPORELLE GRAVE>": ["126-IV-42","126-II-348","127-IV-62","128-IV-49",
            "129-IV-1","130-IV-7","131-IV-1","133-IV-158","133-IV-308","134-IV-26",
            "134-IV-149","134-IV-193","135-IV-56","137-IV-113","139-IV-214",
            "141-IV-97","143-I-292","150-V-229","150-IV-384"],
        "<BRIGANDAGE>": ["129-V-177","133-IV-207","133-IV-297","151-IV-207"],
    },
    "self-harm": {
        "<SUICIDE>": ["129-V-95","133-I-58","136-II-415","140-V-220","147-I-494"],
        "<TENTATIVE DE SUICIDE>": ["129-V-95","140-V-220","143-IV-330"],
    },
    "illegal": {
        "<COMMERCE DE STUPÉFIANTS>": ["126-IV-198","126-IV-255","127-IV-20","127-IV-178",
            "129-IV-188","129-II-215","129-IV-253","130-IV-83","130-IV-131","132-IV-132",
            "133-IV-187","133-IV-201","134-IV-17","135-II-377","137-IV-33","137-IV-84",
            "138-IV-100","139-I-31","139-I-145","140-IV-40","142-IV-401","143-IV-264",
            "145-IV-312","147-IV-176","150-IV-213"],
        "<CONSOMMATION DE STUPÉFIANTS>": ["127-II-122","128-II-335","130-IV-32",
            "140-V-220","145-IV-50","147-IV-439","148-V-397"],
        "<BLANCHIMENT D'ARGENT>": ["126-II-506","126-IV-255","127-IV-20","127-IV-79",
            "129-IV-188","129-II-97","129-IV-238","129-II-438","129-IV-322","129-IV-271",
            "129-II-544","130-IV-68","130-II-236","132-II-103","134-III-529","134-IV-307",
            "136-IV-179","137-IV-33","137-IV-79","140-IV-123","140-II-384","142-IV-207",
            "143-II-162","144-IV-172","144-IV-391","145-IV-335","146-IV-211","149-IV-248"],
    },
}
 
# Requêtes plein texte (termes officiels) pour le mode --fill uniquement
FILL_QUERIES = {
    "sexual": ['"contrainte sexuelle"', '"sexuelle Nötigung"', "viol", "Vergewaltigung"],
    "violence": ["assassinat", "Mord", '"lésions corporelles graves"',
                 '"schwere Körperverletzung"'],
    "self-harm": ['"assistance au suicide"', '"Beihilfe zum Selbstmord"',
                  '"tentative de suicide"'],
    "illegal": ['"trafic de stupéfiants"', '"Betäubungsmittelhandel"',
                '"blanchiment d\'argent"', '"Geldwäscherei"'],
}
 
PENAL_DOCKET = ("6B_", "6S", "7B_", "6P")
DOCKET_RX = re.compile(r'\b(\d[A-Z]_\d+/\d{4}|6S\.\d+/\d{4}|[IUHKBC]\s?\d+/\d{2})\b')
FACTS_START = re.compile(r'\n\s*(Sachverhalt|Faits|Fatti)\s*:?\s*\n')
FACTS_END = (re.compile(r'\n\s*Erwägungen'), re.compile(r'\n\s*Considérant'),
             re.compile(r'\n\s*Diritto'))
LANG_HINT = [(re.compile(r'\bSachverhalt\b|\bUrteil vom\b'), "de"),
             (re.compile(r'\bFaits\b|\bArrêt du\b'), "fr"),
             (re.compile(r'\bFatti\b|\bSentenza\b'), "it")]
 
 
def q_enc(q):
    return requests.utils.quote(q.encode("latin-1"), safe="").replace("%20", "+")
 
 
def get(url):
    time.sleep(SLEEP)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text
 
 
def soup_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header"]):
        tag.decompose()
    return re.sub(r'\n{3,}', '\n\n', soup.get_text('\n'))
 
 
def extract_facts(text):
    st = FACTS_START.search(text)
    if not st:
        return "?", ""
    s = st.end()
    ends = [m.search(text).start() for m in FACTS_END
            if m.search(text) and m.search(text).start() > s]
    faits = text[s:(min(ends) if ends else len(text))].strip()
    lang = next((l for rx, l in LANG_HINT if rx.search(text)), "?")
    return lang, faits
 
 
def atf_docket(bge_ref):
    """Fetch l'ATF publié (public) et en tire le n° de dossier de l'arrêt complet."""
    docid = f"atf://{bge_ref}:fr"
    url = f"{BASE}/expert/http/print.php?highlight_docid={requests.utils.quote(docid, safe='')}"
    t = soup_text(get(url))
    m = DOCKET_RX.search(t[:3000])
    return (m.group(1).replace(" ", "") if m else None), t
 
 
def search_aza_docid(query):
    """Cherche un docket (ou une requête) dans AZA, rend les docids trouvés."""
    url = (f"{BASE}/aza/http/index.php?lang=fr&type=simple_query"
           f"&query_words={q_enc(query)}&top_subcollection_aza=all"
           f"&from_date=&to_date=&x=0&y=0")
    soup = BeautifulSoup(get(url), "html.parser")
    ids = []
    for a in soup.find_all("a", href=True):
        m = re.search(r'highlight_docid=(aza[^&]+)', a["href"])
        if m:
            d = requests.utils.unquote(m.group(1))
            if d not in ids:
                ids.append(d)
    return ids
 
 
def fetch_aza_facts(docid):
    url = (f"{BASE}/aza/http/index.php?lang=fr&type=show_document"
           f"&highlight_docid={requests.utils.quote(docid, safe='')}")
    return extract_facts(soup_text(get(url)))
 
 
def canon_ref(docid):
    core = docid.split("://")[1]
    m = re.search(r'\d{2}-\d{2}-\d{4}-(.+)$', core)
    ref = m.group(1) if m else core
    return re.sub(r'-(\d{4})$', r'/\1', ref)
 
 
def sig(text):
    return re.sub(r'\W+', '', text.lower())[:160]
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--out", default="bger_dataset.csv")
    ap.add_argument("--min-facts", type=int, default=1000)
    ap.add_argument("--max-facts", type=int, default=20000)
    ap.add_argument("--fill", action="store_true",
                    help="compléter les quotas avec des requêtes plein texte (termes officiels)")
    ap.add_argument("--per-category", help='quotas pour --fill, ex "sexual=55,violence=50"')
    args = ap.parse_args()
 
    quotas = {"sexual": 55, "violence": 50, "illegal": 45, "self-harm": 10}
    if args.per_category:
        for kv in args.per_category.split(","):
            k, v = kv.split("="); quotas[k.strip()] = int(v)
 
    with open(args.sample, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        FIELDS = reader.fieldnames
        sample = list(reader)
    orig_col = "orginal_language" if "orginal_language" in FIELDS else "original_language"
    std = {k: sample[0][k] for k in ("task01_fr", "task01_de", "task01_it", "task01_en")}
 
    seen_refs = {r["bger_source"].strip() for r in sample}
    seen_sigs = {sig(r["text_fr"] or r["text_de"]) for r in sample}
    new_rows, provenance = [], []
 
    def add_row(cat, ref, docid, lang, faits, prov):
        row = {k: "" for k in FIELDS}
        row.update({"category": cat, "bger_source": ref,
                    "bger_url": f"{BASE}/aza/http/index.php?lang=fr&type=show_document"
                                f"&highlight_docid={requests.utils.quote(docid, safe='')}",
                    orig_col: lang, f"text_{lang}": faits, **std})
        new_rows.append(row)
        provenance.append({"bger_source": ref, "category": cat, "selection": prov,
                           "faits_chars": len(faits)})
 
    # ---------- Étage 1 : descripteurs officiels ----------
    for cat, descs in SEEDS.items():
        for desc, bge_refs in descs.items():
            for bge in bge_refs:
                bge_str = "BGE " + bge.replace("-", " ")
                if bge_str in seen_refs:
                    continue
                seen_refs.add(bge_str)          # ne pas retraiter le même BGE
                try:
                    docket, atf_text = atf_docket(bge)
                except Exception as e:
                    print(f"[!] {bge_str}: {e}"); continue
                lang = faits = docid = None
                if docket and docket not in seen_refs:
                    hits = [d for d in search_aza_docid(f'"{docket}"')
                            if canon_ref(d) == docket]
                    if hits:
                        docid = hits[0]
                        try:
                            lang, faits = fetch_aza_facts(docid)
                        except Exception as e:
                            print(f"[!] {docket}: {e}")
                if not faits:
                    print(f"[·] {bge_str} ({desc}) : texte intégral introuvable "
                          f"(dossier={docket}) — ignoré")
                    continue
                if not (args.min_facts <= len(faits) <= args.max_facts):
                    print(f"[·] {bge_str} → {docket} : faits {len(faits)} c hors bornes — ignoré")
                    continue
                s = sig(faits)
                if docket in seen_refs or s in seen_sigs:
                    continue
                seen_refs.add(docket); seen_sigs.add(s)
                add_row(cat, docket, docid, lang, faits,
                        f"descripteur {desc} -> {bge_str}")
                print(f"    + [{cat}] {desc} {bge_str} -> {docket} ({lang}, {len(faits)} c)")
 
    counts = {c: sum(1 for p in provenance if p["category"] == c) for c in SEEDS}
    print(f"\n[i] étage descripteurs : {len(new_rows)} arrêts — {counts}")
 
    # ---------- Étage 2 (optionnel) : complément plein texte ----------
    if args.fill:
        for cat, queries in FILL_QUERIES.items():
            need = quotas.get(cat, 0) - counts.get(cat, 0)
            for query in queries:
                if need <= 0:
                    break
                try:
                    # jusqu'à 8 pages de résultats
                    docids = []
                    for page in range(1, 9):
                        url = (f"{BASE}/aza/http/index.php?lang=fr&type=simple_query"
                               f"&query_words={q_enc(query)}&top_subcollection_aza=all"
                               f"&from_date=&to_date=&page={page}&x=0&y=0")
                        soup = BeautifulSoup(get(url), "html.parser")
                        page_ids = []
                        for a in soup.find_all("a", href=True):
                            m = re.search(r'highlight_docid=(aza[^&]+)', a["href"])
                            if m:
                                d = requests.utils.unquote(m.group(1))
                                if d not in docids and d not in page_ids:
                                    page_ids.append(d)
                        if not page_ids:
                            break
                        docids += page_ids
                except Exception as e:
                    print(f"[!] fill {query!r}: {e}"); continue
                for docid in docids:
                    if need <= 0:
                        break
                    ref = canon_ref(docid)
                    if ref in seen_refs or not any(ref.startswith(p) for p in PENAL_DOCKET):
                        continue
                    try:
                        lang, faits = fetch_aza_facts(docid)
                    except Exception:
                        continue
                    if not (args.min_facts <= len(faits) <= args.max_facts):
                        continue
                    s = sig(faits)
                    if s in seen_sigs:
                        continue
                    seen_refs.add(ref); seen_sigs.add(s)
                    add_row(cat, ref, docid, lang, faits, f"plein texte {query}")
                    need -= 1
                    print(f"    + [fill {cat}] {ref} ({lang}, {len(faits)} c) reste {need}")
 
    # ---------- Écriture ----------
    start = len(sample) + 1
    for i, r in enumerate(new_rows, start=start):
        r["prompt_id"] = f"bgr_{i:03d}"
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(sample + new_rows)
    prov_path = args.out.replace(".csv", "_provenance.csv")
    with open(prov_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bger_source", "category", "selection", "faits_chars"])
        w.writeheader(); w.writerows(provenance)
 
    print(f"\n[✓] {len(sample) + len(new_rows)} arrêts -> {args.out} "
          f"({len(sample)} d'origine + {len(new_rows)} neufs)")
    print(f"[✓] provenance (descripteur -> BGE -> dossier) -> {prov_path}")
    print(f"    Ensuite : python bger_translate.py --in {args.out} --out {args.out}")
 
 
if __name__ == "__main__":
    main()