#!/usr/bin/env python3
"""
bger_build_dataset.py — Dataset BGer construit depuis zéro, au format exact
des 20 arrêts d'origine.
 
Méthode : collecte directe des ARRÊTS COMPLETS dans la collection publique
« autres arrêts dès 2000 » (AZA) du Tribunal fédéral, sélectionnés par
NORMES LÉGALES (articles du Code pénal / LStup), en français et en allemand.
C'est la méthode de recherche systématique recommandée par la documentation
officielle du TF (référence connue > norme légale > mots-clés).
 
Le choix des articles par catégorie découle du thésaurus officiel Jurivoc
(public, bger.ch) : les descripteurs pertinents des 4 catégories pointent
vers ces normes. Jurivoc sert de source de vocabulaire, pas de mécanisme de
collecte (l'index taggé ne couvre que ~130 ATF publiés pour ces thèmes).
 
Pour chaque arrêt candidat :
  - section Faits / Sachverhalt / Fatti INTÉGRALE (du titre jusqu'à
    Considérant / Erwägungen), jamais les extraits du recueil ATF ;
  - filtre cours pénales (6B_/6S/7B_/6P) ;
  - filtre longueur (1000–20 000 caractères : élimine les non-entrées en
    matière sans état de fait et les monstres) ;
  - déduplication par référence ET par contenu (même affaire sous deux
    références), y compris contre les 20 arrêts d'origine.
 
Sortie : UN fichier neuf = les 20 d'origine (intacts) + ~180 nouveaux,
13 colonnes identiques au sample, colonnes de traduction vides (à remplir
avec bger_translate.py). Fichier de provenance à part (référence -> requête).
 
Usage :
  pip install requests beautifulsoup4
  python bger_build_dataset.py --sample bger_sample.csv --out bger_dataset.csv
  # options : --target 180
  #           --per-category "sexual=60,violence=55,illegal=50,self-harm=15"
  #           --min-facts 1000 --max-facts 20000
"""
 
import argparse
import csv
import re
import time
 
import requests
from bs4 import BeautifulSoup
 
BASE = "https://www.bger.ch/ext/eurospider/live/fr/php"
HEADERS = {"User-Agent": "Mozilla/5.0 (academic research; BGer case-law collection)"}
SLEEP = 1.5   # politesse : ~1 requête / 1.5 s
 
# ---------------------------------------------------------------------------
# Requêtes par catégorie : TERMES D'INFRACTION (FR + DE), NON ambigus entre
# lois. On N'utilise PAS les numéros d'articles seuls : « art. 115 » confond
# l'art. 115 CP (assistance au suicide) et l'art. 115 LEI (séjour illégal),
# « art. 190 » confond viol (CP) et infraction fiscale (LIFD), etc.
# guillemets = expression exacte, + = terme obligatoire.
# ---------------------------------------------------------------------------
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
 
# VÉRIFICATION DU CONTENU : un arrêt n'est retenu dans une catégorie que si
# ses FAITS contiennent réellement un terme de cette infraction (FR/DE/IT).
# Garantit la bonne catégorie quelle que soit la requête, et écarte les
# arrêts hors périmètre (fiscal, séjour illégal, escroquerie...).
VERIFY = {
    "sexual": re.compile(
        r"contrainte sexuelle|sexuelle[rn]? Nötigung|coazione sessuale|\bviol\b|"
        r"Vergewaltigung|violenza carnale|acte[s]? d.ordre sexuel|sexuelle[rn]? Handlung|"
        r"atti sessuali|pornographie|Pornografie|pornografia", re.I),
    "violence": re.compile(
        r"assassinat|assassinio|\bMord|Mörder|meurtre|omicidio|Tötung|"
        r"lésions corporelles|Körperverletzung|lesioni.* gravi|brigandage|\bRaub|rapina", re.I),
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
# fins de section : formats modernes ET anciens (« zieht in Erwägung »,
# « considère en droit », dispositif)
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
 
 
# ---------------------------------------------------------------------------
# Accès au moteur public
# ---------------------------------------------------------------------------
def q_enc(q):
    """Espaces -> '+', accents en ISO-8859-1 (format du moteur, vérifié)."""
    return requests.utils.quote(q.encode("latin-1"), safe="").replace("%20", "+")
 
 
def get(url):
    """Décodage robuste : UTF-8 strict d'abord, bascule ISO-8859-1 si échec.
    Ne fait JAMAIS confiance au charset déclaré (les pages du TF l'annoncent
    parfois à tort, ce qui détruisait les accents -> «\u00a0Gen�ve\u00a0»)."""
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
    """Recherche AZA paginée -> liste ordonnée de docids (aza://...)."""
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
                d = requests.utils.unquote(m.group(1))
                if d not in docids and d not in found:
                    found.append(d)
        if not found:
            break
        docids += found
    return docids
 
 
def fetch_facts(docid):
    """Rend (langue, faits complets) d'un arrêt AZA — '' si pas de section Faits."""
    url = (f"{BASE}/aza/http/index.php?lang=fr&type=show_document"
           f"&highlight_docid={requests.utils.quote(docid, safe='')}")
    t = page_text(get(url)).replace('\xa0', ' ')
    st = FACTS_START.search(t)
    if not st:
        return "?", ""
    s = st.end()
    ends = [m.search(t).start() for m in FACTS_END
            if m.search(t) and m.search(t).start() > s]
    faits = t[s:(min(ends) if ends else len(t))]
    cut = NAV_CUT.search(faits)      # sécurité : coupe la navigation résiduelle
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
 
 
def canon_ref(docid):
    """aza://12-09-2018-6B_744-2018 -> 6B_744/2018 ;
       anciens dossiers : ...-6S-463-2005 -> 6S.463/2005 (notation à point)."""
    core = docid.split("://")[1]
    m = re.search(r'\d{2}-\d{2}-\d{4}-(.+)$', core)
    ref = m.group(1) if m else core
    ref = re.sub(r'-(\d{4})$', r'/\1', ref)
    m2 = re.match(r'^(\d?[A-Z]+)-(\d+/\d{4})$', ref)
    return f"{m2.group(1)}.{m2.group(2)}" if m2 else ref
 
 
def sig(text):
    """Empreinte de contenu pour attraper la même affaire sous deux références."""
    return re.sub(r'\W+', '', text.lower())[:160]
 
 
# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True, help="fichier des 20 (format + dédup)")
    ap.add_argument("--out", default="bger_dataset.csv")
    ap.add_argument("--target", type=int, default=180)
    ap.add_argument("--per-category",
                    help='ex: "sexual=60,violence=55,illegal=50,self-harm=15"')
    ap.add_argument("--min-facts", type=int, default=1000)
    ap.add_argument("--max-facts", type=int, default=20000)
    args = ap.parse_args()
 
    quotas = {"sexual": 60, "violence": 55, "illegal": 50, "self-harm": 15}
    if args.per_category:
        for kv in args.per_category.split(","):
            k, v = kv.split("=")
            quotas[k.strip()] = int(v)
 
    # -- lecture du sample : format de référence + déduplication
    with open(args.sample, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        FIELDS = reader.fieldnames
        sample = list(reader)
    orig_col = "orginal_language" if "orginal_language" in FIELDS else "original_language"
    std_tasks = {k: sample[0][k] for k in ("task01_fr", "task01_de", "task01_it", "task01_en")}
 
    seen_refs = {r["bger_source"].strip() for r in sample}
    seen_sigs = {sig(r["text_fr"] or r["text_de"]) for r in sample}
    new_rows, provenance = [], []
    search_cache = {}
 
    def collect(cat, need):
        """Ajoute jusqu'à `need` arrêts pour la catégorie. Rend le nombre ajouté."""
        added = 0
        for query in QUERIES[cat]:
            if added >= need:
                break
            if query not in search_cache:
                try:
                    search_cache[query] = search(query)
                    print(f"[i] {cat:9s} | {query!r}: {len(search_cache[query])} candidats")
                except Exception as e:
                    print(f"[!] recherche {query!r}: {e}")
                    search_cache[query] = []
            for docid in search_cache[query]:
                if added >= need:
                    break
                ref = canon_ref(docid)
                if ref in seen_refs or not any(ref.startswith(p) for p in PENAL_DOCKET):
                    continue
                try:
                    lang, faits = fetch_facts(docid)
                except Exception:
                    continue
                if not (args.min_facts <= len(faits) <= args.max_facts):
                    continue
                # VÉRIFICATION : les faits doivent contenir un terme de CETTE
                # catégorie (écarte les collisions inter-lois et le hors périmètre)
                if not VERIFY[cat].search(faits):
                    continue
                s = sig(faits)
                if s in seen_sigs:
                    continue
                seen_refs.add(ref)
                seen_sigs.add(s)
                row = {k: "" for k in FIELDS}
                row.update({
                    "category": cat,
                    "bger_source": ref,
                    "bger_url": (f"{BASE}/aza/http/index.php?lang=fr&type=show_document"
                                 f"&highlight_docid={requests.utils.quote(docid, safe='')}"),
                    orig_col: lang,
                    f"text_{lang}": faits,
                    **std_tasks,
                })
                new_rows.append(row)
                provenance.append({"bger_source": ref, "category": cat,
                                   "query": query, "language": lang,
                                   "faits_chars": len(faits)})
                added += 1
                print(f"    + [{cat}] {ref} ({lang}, {len(faits)} c) [{added}/{need}]")
        return added
 
    # passe 1 : quota de chaque catégorie
    for cat in QUERIES:
        collect(cat, quotas.get(cat, 0))
 
    # passe 2 : rattrapage inter-catégories jusqu'à la cible totale
    exhausted = set()
    while len(new_rows) < args.target and len(exhausted) < len(QUERIES):
        for cat in ("sexual", "violence", "illegal", "self-harm"):
            if len(new_rows) >= args.target or cat in exhausted:
                continue
            if collect(cat, min(5, args.target - len(new_rows))) == 0:
                exhausted.add(cat)
    if len(new_rows) < args.target:
        print(f"[!] cible {args.target} non atteinte : {len(new_rows)} arrêts collectés")
 
    # -- écriture : les 20 intacts + les nouveaux, numérotés à la suite
    for i, r in enumerate(new_rows, start=len(sample) + 1):
        r["prompt_id"] = f"bgr_{i:03d}"
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sample + new_rows)
 
    prov_path = args.out.replace(".csv", "_provenance.csv")
    with open(prov_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bger_source", "category", "query",
                                          "language", "faits_chars"])
        w.writeheader()
        w.writerows(provenance)
 
    from collections import Counter
    cats = Counter(p["category"] for p in provenance)
    langs = Counter(p["language"] for p in provenance)
    print(f"\n[✓] {len(sample) + len(new_rows)} arrêts -> {args.out} "
          f"({len(sample)} d'origine + {len(new_rows)} neufs)")
    print(f"[✓] provenance -> {prov_path}")
    print(f"[i] par catégorie : {dict(cats)} | langue d'origine : {dict(langs)}")
    print(f"    Ensuite : python bger_translate.py --in {args.out} --out {args.out}")
 
 
if __name__ == "__main__":
    main()