#!/usr/bin/env python3
"""
cedh_build_dataset.py — Collecte ~200 arrêts CEDH (HUDOC) à faits sensibles,
méthodologie SYMÉTRIQUE à bger_build_dataset.py (mêmes catégories, mêmes
garde-fous, même format de sortie 13 colonnes).

Source : API JSON de HUDOC (celle du site lui-même, utilisée par les projets
académiques echr-extractor / echr-scraping) :
  - liste     : https://hudoc.echr.coe.int/app/query/results?query=...&select=...&start=0&length=500
  - plein texte: https://hudoc.echr.coe.int/app/conversion/docx/html/body?library=ECHR&id=<itemid>
                 (secours .docx : /app/conversion/docx/?library=ECHR&id=<itemid>&filename=doc.docx)

Sélection par catégorie (comme BGer : termes d'infraction en plein texte,
PAS de numéros d'articles nationaux ; le filtre `article:` de la Convention est
un métadonnée HUDOC propre, utilisé en appui) + VÉRIFICATION du contenu des
faits par regex (leçon BGer : jamais confiance à la seule requête).

Bilinguisme (le gain méthodologique vs BGer) : les arrêts existent en anglais
et/ou français officiels ; l'appariement EN<->FR se fait par numéro de requête
(appno). Priorité aux affaires disponibles DANS LES DEUX LANGUES -> text_en ET
text_fr authentiques ; complément monolingue si les quotas ne sont pas atteints.
DE/IT ensuite via bger_translate.py (inchangé).

Extraction des faits : section « THE FACTS » (ou « AS TO THE FACTS ») jusqu'à
« THE LAW » / « EN FAIT » jusqu'à « EN DROIT » — l'équivalent Sachverhalt->
Erwägungen du BGer.

⚠️ À lancer depuis TA machine (le conteneur de travail est derrière un proxy).
   Politesse : 1 requête / 1.5 s, User-Agent académique neutre.

Usage :
  pip install requests beautifulsoup4
  # 1) sonde (vérifie la syntaxe de requête et les volumes, ne télécharge rien)
  python cedh_build_dataset.py --probe
  # 2) collecte complète
  python cedh_build_dataset.py --base data/bger_dataset.csv --out data/cedh_dataset.csv
  # options : --target 200 --min-facts 1000 --max-facts 12000 --bilingual-only

Étapes suivantes (pipeline inchangé) :
  python bger_translate.py --in data/cedh_dataset.csv --out data/cedh_dataset.csv --max-chars 980000
  python add_prefix_condition.py --in data/cedh_dataset.csv --out data/cedh_dataset.csv
  python split_paragraphs.py --all --csv data/cedh_dataset.csv --out cedh_para.csv --write
  python run_tf.py --prompts-file data/cedh_dataset.csv --task-mode all ...
"""

import argparse
import collections
import csv
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://hudoc.echr.coe.int"
HEADERS = {"User-Agent": "Mozilla/5.0 (academic research; ECtHR case-law collection)"}
SLEEP = 1.5

SELECT = ("itemid,docname,appno,doctype,doctypebranch,importance,kpdate,"
          "languageisocode,article,conclusion,documentcollectionid2,ecli")

# --- Sélection par catégorie : termes plein-texte EN/FR + articles Convention en appui
QUERIES = {
    "sexual": {
        "articles": ["3", "8"],
        "en": ['"rape"', '"sexual abuse"', '"sexual assault"', '"sexual violence"'],
        "fr": ['"viol"', '"abus sexuels"', '"agression sexuelle"', '"violences sexuelles"'],
    },
    "violence": {
        "articles": ["2", "3"],
        "en": ['"torture"', '"ill-treatment"', '"beaten"', '"stabbed"', '"killed her"', '"killed him"'],
        "fr": ['"torture"', '"mauvais traitements"', '"coups de couteau"', '"passé à tabac"'],
    },
    "self-harm": {
        "articles": ["2"],
        "en": ['"committed suicide"', '"hanged himself"', '"self-harm"', '"assisted suicide"'],
        "fr": ['"s\'est suicidé"', '"s\'est pendu"', '"automutilation"', '"suicide assisté"'],
    },
    "illegal": {
        "articles": ["5", "6", "8"],
        "en": ['"drug trafficking"', '"money laundering"', '"criminal organisation"', '"heroin"'],
        "fr": ['"trafic de stupéfiants"', '"blanchiment"', '"organisation criminelle"', '"héroïne"'],
    },
}
# Vérification de contenu des FAITS (leçon BGer) — bilingue EN/FR
VERIFY = {
    # NB « viol » : exclure « violation » (présent dans tout arrêt CEDH fr) et
    # « violence/violemment » (pas spécifiquement sexuel) tout en attrapant
    # violé/violée/violer/violeur/viols.
    "sexual": re.compile(r"rape|sexual (abuse|assault|violence|intercourse)|\bviol(?!ation|ence|emment)\w*|abus sexuel|agression sexuelle|violences sexuelles", re.I),
    "violence": re.compile(r"torture|ill-?treat|beaten|stabbed|killed|murder|meurtre|mauvais traitements|coups|assassin", re.I),
    "self-harm": re.compile(r"suicide|hanged|self-?harm|automutilation|se pendre|s'est pendu", re.I),
    "illegal": re.compile(r"drug|trafficking|heroin|cocaine|money laundering|stupéfiants|blanchiment|criminal organi[sz]ation|organisation criminelle|héroïne|cocaïne", re.I),
}
# Quotas miroirs du dataset BGer
QUOTAS = {"sexual": 75, "violence": 59, "illegal": 51, "self-harm": 15}

FACTS_START = re.compile(r'\b(AS TO THE FACTS|THE FACTS|EN FAIT)\b')
# Démarrage préféré : les circonstances de l'espèce (saute le boilerplate)
CIRC = re.compile(r"THE CIRCUMSTANCES OF THE CASE|LES CIRCONSTANCES DE L['’]ESP[ÈE]CE")
# Fin : LE DROIT — mais aussi le CADRE LÉGAL INTERNE, sous-section de THE FACTS
# (l'équivalent CEDH de la fuite de considérants BGer)
FACTS_END = re.compile(r"RELEVANT (DOMESTIC|LEGAL|INTERNATIONAL|COUNCIL OF EUROPE)[A-Z ,'’\-]*|"
                       r"LE DROIT (INTERNE|ET LA PRATIQUE)[A-ZÉÈ ,'’\-]*|"
                       r"DROIT INTERNE PERTINENT|LE CADRE JURIDIQUE[A-ZÉÈ ,'’\-]*|"
                       r"TEXTES? (INTERNES? )?PERTINENTS?|"
                       r'\b(AS TO THE LAW|THE LAW|EN DROIT|FOR THESE REASONS|PAR CES MOTIFS|'
                       r'PROCEEDINGS BEFORE THE COMMISSION)\b')

TITLE_LINE = re.compile(r"^([IVXLC]+\.?|[A-Z]\.|[A-Z][A-Z '’&,\-]{3,})$")
NUM_LINE = re.compile(r"^(\d{1,3})\s*\.?\s*$")
DOT_LINE = re.compile(r"^\.\s*$")
NUM_INLINE = re.compile(r"^(\d{1,3})\.\s+\S")   # « N. texte » sur une seule ligne
ALPHA_HEAD = re.compile(r"^\([a-z]\)\s+\S")      # « (a) … » titre de sous-sous-section


def normalize_paragraphs(text):
    """Une ligne par paragraphe numéroté CEDH (numéros recollés, phrases
    recousues) ; titres sur lignes à part (filtrés ensuite par longueur)."""
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
        m = NUM_LINE.match(s)
        if m:
            flush()
            cur = m.group(1) + ". "
            j = i + 1
            while j < len(lines) and not lines[j]:
                j += 1
            if j < len(lines) and DOT_LINE.match(lines[j]):
                i = j
        elif NUM_INLINE.match(s):        # « N. texte » inline -> nouveau §
            flush()
            cur = s
        elif ALPHA_HEAD.match(s):        # « (a) … » titre, ligne à part
            flush()
            out.append(s)
        elif TITLE_LINE.match(s):
            flush()
            out.append(s)
        else:
            cur += (" " if cur else "") + s
        i += 1
    flush()
    # purge les titres/numéros orphelins en fin de texte
    while out and (TITLE_LINE.match(out[-1]) or NUM_LINE.match(out[-1])):
        out.pop()
    return "\n".join(out)


def get(url, **kw):
    time.sleep(SLEEP)
    r = requests.get(url, headers=HEADERS, timeout=40, **kw)
    r.raise_for_status()
    return r


def search(category, lang_iso, term, article=None, length=200):
    """Une requête HUDOC ; retourne la liste des 'columns' des résultats."""
    parts = ['(contentsitename:ECHR)',
             '(documentcollectionid2:"JUDGMENTS")',
             f'(languageisocode:"{lang_iso}")',
             term]
    if article:
        parts.append(f'(article:"{article}")')
    query = " AND ".join(parts)
    url = f"{BASE}/app/query/results"
    r = get(url, params={"query": query, "select": SELECT,
                         "sort": "", "start": 0, "length": length})
    data = r.json()
    return data.get("resultcount", 0), [x.get("columns", {}) for x in data.get("results", [])]


def fetch_text(itemid):
    """Plein texte d'un document (HTML body ; secours docx non implémenté ici)."""
    url = f"{BASE}/app/conversion/docx/html/body"
    r = get(url, params={"library": "ECHR", "id": itemid})
    try:
        html = r.content.decode("utf-8")
    except UnicodeDecodeError:
        html = r.content.decode("latin-1")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    t = soup.get_text("\n").replace("\xa0", " ")
    return re.sub(r'\n{3,}', '\n\n', t)


def extract_facts(text):
    st = FACTS_START.search(text)
    if not st:
        return ""
    s = st.end()
    # démarrage préféré : circonstances de l'espèce (saute le boilerplate)
    c = CIRC.search(text, s)
    if c:
        s = c.end()
    en = FACTS_END.search(text, s)
    facts = text[s:en.start()] if en else text[s:]
    # reconstruction (une ligne par § numéroté) puis filtrage strict :
    # seules les lignes « N. … » sont conservées — les titres de sections
    # disparaissent, il ne reste que les paragraphes officiels de l'arrêt.
    return keep_numbered(normalize_paragraphs(facts))


NUM_PREFIX = re.compile(r"^(\d{1,3})\.\s")


def keep_numbered(text):
    return "\n".join(l for l in text.split("\n") if NUM_PREFIX.match(l))


def para_map(text):
    """dict numéro -> ligne pour les lignes « N. … » (première occurrence)."""
    m = {}
    for line in (text or "").split("\n"):
        mm = NUM_PREFIX.match(line)
        if mm:
            n = int(mm.group(1))
            if n not in m:
                m[n] = line
    return m


def align_bilingual(facts_en, facts_fr):
    """Aligne les versions officielles EN et FR PAR NUMÉRO DE § (la numérotation
    est commune aux deux langues) : on garde l'intersection des numéros, dans
    l'ordre. Alignement garanti par construction — plus robuste que l'égalité
    des retours de ligne. Retourne (en, fr) ; fr='' si rien d'alignable."""
    me, mf = para_map(facts_en), para_map(facts_fr)
    common = sorted(set(me) & set(mf))
    if len(common) < 3:
        return facts_en, ""
    en2 = "\n".join(me[n] for n in common)
    fr2 = "\n".join(mf[n] for n in common)
    # garde-fou sémantique : les nombres (dates) doivent concorder § par §,
    # sinon le FR est un autre document -> on N'AMPUTE PAS l'anglais.
    if _pair_score(en2, fr2) < 0.55:
        return facts_en, ""
    return en2, fr2


def first_appno(cols):
    return (cols.get("appno") or "").split(";")[0].strip()


def find_pair(appno, want_iso, kpdate):
    """Version linguistique du MÊME ARRÊT : même appno ET même date de
    prononcé (kpdate). Sans ce garde-fou, l'appno peut ramener un autre
    document de la même affaire (décision de recevabilité, autre arrêt),
    avec sa propre numérotation de §§."""
    try:
        _, res = search("", want_iso, f'(appno:"{appno}")')
    except Exception:
        return None
    same_date = [c for c in res if c.get("kpdate", "")[:10] == (kpdate or "")[:10]]
    for c in same_date:
        if c.get("doctype", "").startswith("HEJUD") or c.get("documentcollectionid2") == "JUDGMENTS":
            return c
    return same_date[0] if same_date else None


NUMS_IN_PARA = re.compile(r"\b\d{1,4}\b")


def _pair_score(en, fr):
    """Concordance des nombres § par § (invariants entre langues)."""
    scores = []
    for a, b in zip(en.split("\n"), fr.split("\n")):
        na = set(NUMS_IN_PARA.findall(a.split(".", 1)[-1]))
        nb = set(NUMS_IN_PARA.findall(b.split(".", 1)[-1]))
        if na or nb:
            scores.append(len(na & nb) / max(1, len(na | nb)))
    return sum(scores) / len(scores) if scores else 1.0


def sig(t):
    return re.sub(r'\W+', '', (t or "").lower())[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="teste la syntaxe et affiche les volumes")
    ap.add_argument("--base", default="data/bger_dataset.csv",
                    help="dataset BGer (source des task01_*)")
    ap.add_argument("--out", default="data/cedh_dataset.csv")
    ap.add_argument("--target", type=int, default=200)
    ap.add_argument("--min-facts", type=int, default=1000)
    ap.add_argument("--max-facts", type=int, default=12000)
    ap.add_argument("--bilingual-only", action="store_true",
                    help="ne garde QUE les affaires disponibles en EN ET FR")
    args = ap.parse_args()

    if args.probe:
        print("[probe] une requête par catégorie (EN, 1er terme, 1er article) :")
        for cat, q in QUERIES.items():
            try:
                n, res = search(cat, "ENG", q["en"][0], q["articles"][0], length=3)
                name = res[0].get("docname", "?") if res else "-"
                print(f"  {cat:<10} -> {n:>6} résultats | ex.: {name[:70]}")
            except Exception as e:
                print(f"  {cat:<10} -> ERREUR : {e}")
        print("[probe] si une catégorie affiche ERREUR ou 0, ajuster la syntaxe "
              "de search() (voir commentaire) avant la collecte.")
        return

    # tasks standard reprises du dataset BGer (mêmes 4 langues)
    with open(args.base, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        base_fields = rd.fieldnames
        std = next(rd)
    FIELDS = ["prompt_id", "category", "bger_source", "bger_url",
              "task01_fr", "task01_de", "task01_it", "task01_en",
              "orginal_language", "text_fr", "text_de", "text_it", "text_en"]
    task = {k: std[k] for k in ("task01_fr", "task01_de", "task01_it", "task01_en")}

    rows, seen_app, seen_sig = [], set(), set()
    need = dict(QUOTAS)
    total_target = min(args.target, sum(QUOTAS.values()))

    for cat, q in QUERIES.items():
        for term in q["en"]:
            if need[cat] <= 0:
                break
            for article in q["articles"]:
                if need[cat] <= 0:
                    break
                try:
                    n, res = search(cat, "ENG", term, article)
                except Exception as e:
                    print(f"[!] {cat}/{term}/{article}: {e}")
                    continue
                print(f"[i] {cat} | {term} | art.{article} -> {n} résultats")
                for c in res:
                    if need[cat] <= 0:
                        break
                    appno = first_appno(c)
                    if not appno or appno in seen_app:
                        continue
                    itemid = c.get("itemid")
                    if not itemid:
                        continue
                    try:
                        facts_en = extract_facts(fetch_text(itemid))
                    except Exception as e:
                        print(f"    [!] {itemid}: {e}")
                        continue
                    if not (args.min_facts <= len(facts_en) <= args.max_facts):
                        continue
                    if not VERIFY[cat].search(facts_en):
                        continue
                    s = sig(facts_en)
                    if s in seen_sig:
                        continue
                    # appariement FR + alignement par numéro de §
                    facts_fr = ""
                    pair = find_pair(appno, "FRE", c.get("kpdate", ""))
                    if pair and pair.get("itemid"):
                        try:
                            ffr = extract_facts(fetch_text(pair["itemid"]))
                            if args.min_facts <= len(ffr) <= args.max_facts * 2:
                                facts_en, facts_fr = align_bilingual(facts_en, ffr)
                        except Exception:
                            pass
                    if len(facts_en) < args.min_facts:
                        continue          # trop court après alignement
                    if args.bilingual_only and not facts_fr:
                        continue
                    seen_app.add(appno)
                    seen_sig.add(s)
                    need[cat] -= 1
                    row = {k: "" for k in FIELDS}
                    row.update({
                        "category": cat,
                        "bger_source": f"CEDH {c.get('docname','?')} ({appno})",
                        "bger_url": f"{BASE}/eng?i={itemid}",
                        "orginal_language": "en",
                        "text_en": facts_en, "text_fr": facts_fr,
                        **task,
                    })
                    rows.append(row)
                    both = "EN+FR" if facts_fr else "EN seul"
                    print(f"    + [{cat}] {c.get('docname','?')[:60]} ({both}, "
                          f"{len(facts_en)} c) [{QUOTAS[cat]-need[cat]}/{QUOTAS[cat]}]")
                    if len(rows) >= total_target:
                        break

    for i, r in enumerate(rows, 1):
        r["prompt_id"] = f"cedh_{i:03d}"
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    bil = sum(1 for r in rows if r["text_fr"])
    print(f"\n[✓] {len(rows)} affaires écrites ({bil} bilingues EN+FR authentiques) -> {args.out}")
    print(f"[i] par catégorie : {dict(collections.Counter(r['category'] for r in rows))}")
    print("[i] étape suivante : bger_translate.py (complète DE/IT — et FR là où absent),")
    print("    puis add_prefix_condition.py, split_paragraphs.py, run_tf.py — inchangés.")


if __name__ == "__main__":
    main()
