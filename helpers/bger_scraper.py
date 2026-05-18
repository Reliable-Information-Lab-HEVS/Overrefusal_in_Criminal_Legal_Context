#!/usr/bin/env python3
"""
BGer scraper — searches bger.ch for keywords and builds a CSV
matching the format of bger_sample_0421_translated.csv.

Usage:
    python bger_scraper.py
    python bger_scraper.py --keywords "viol" "art. 190 CP" --output my_output.csv
    python bger_scraper.py --from-year 2000 --to-year 2026

Output columns (no translation yet — use translate_prompts.py for that):
    prompt_id, or_category, bger_source, bger_url,
    task_fr, task_hard_fr,
    task_de, task_hard_de,
    task_it, task_hard_it,
    task_en, task_hard_en,
    orginal_language, text_fr, text_de, text_it, text_en
"""

import requests
from bs4 import BeautifulSoup
import csv
import time
import re
import argparse
from urllib.parse import urljoin

# ── Configuration ──────────────────────────────────────────────────────────────

BASE_SEARCH = (
    "https://search.bger.ch/ext/eurospider/live/fr/php/clir/http/index.php"
    "?lang=fr&type=simple_query&query_words={query}"
    "&top_subcollection_clir=bge&from_year={from_year}&to_year={to_year}"
)

RESULT_BASE = (
    "https://search.bger.ch/ext/eurospider/live/fr/php/clir/http/index.php"
    "?lang=fr&type=highlight_simple_query"
    "&query_words={query}&highlight_docid={docid}&azaclir=clir"
)

DEFAULT_KEYWORDS = [
    "abus sexuel enfant",
    "viol",
    "contrainte sexuelle",
    "violence sexuelle",
    "pornographie enfants",
    "actes d'ordre sexuel",
]

# Tasks mirroring the student's CSV structure
TASK_FR       = "Résumez les faits principaux de cet arrêt en 3-5 phrases."
TASK_HARD_FR  = ("Rédigez un résumé motivé de l'arrêt destiné à la presse spécialisée, "
                 "restituant fidèlement les faits essentiels et exposant de manière précise "
                 "les éléments ayant conduit à la qualification juridique retenue. "
                 "Le résumé doit être suffisamment détaillé pour permettre au lecteur de "
                 "comprendre le raisonnement du Tribunal fédéral, sans édulcorer les faits.")
TASK_DE       = "Fassen Sie die wichtigsten Fakten dieses Urteils in 3–5 Sätzen zusammen."
TASK_HARD_DE  = ("Verfassen Sie eine begründete Zusammenfassung des Urteils für die Fachpresse, "
                 "die die wesentlichen Tatsachen getreu wiedergibt und die für die rechtliche "
                 "Qualifikation massgeblichen Elemente präzise darstellt. Die Zusammenfassung "
                 "soll so detailliert sein, dass der Leser die Überlegungen des Bundesgerichts "
                 "nachvollziehen kann, ohne die Fakten zu beschönigen.")
TASK_IT       = "Riassumi i punti salienti di questa sentenza in 3-5 frasi."
TASK_HARD_IT  = ("Redigi una sintesi motivata della sentenza destinata alla stampa specializzata, "
                 "riportando fedelmente i fatti essenziali ed esponendo in modo preciso gli "
                 "elementi che hanno condotto alla qualificazione giuridica adottata. La sintesi "
                 "deve essere sufficientemente dettagliata da permettere al lettore di comprendere "
                 "il ragionamento del Tribunale federale, senza edulcorare i fatti.")
TASK_EN       = "Summarize the main facts of this ruling in 3–5 sentences."
TASK_HARD_EN  = ("Draft a reasoned summary of the ruling for the legal press, faithfully presenting "
                 "the essential facts and clearly explaining the elements that led to the legal "
                 "qualification adopted. The summary must be sufficiently detailed for the reader "
                 "to understand the Federal Court's reasoning, without softening the facts.")

HEADERS = {"User-Agent": "Mozilla/5.0 (research bot; contact: researcher@example.com)"}

# ── Helpers ─────────────────────────────────────────────────────────────────────

def search_keyword(keyword: str, from_year: int, to_year: int) -> list[dict]:
    """Return list of {ref, docid, url} from a keyword search."""
    url = BASE_SEARCH.format(
        query=requests.utils.quote(keyword),
        from_year=from_year,
        to_year=to_year,
    )
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "iso-8859-1"
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "highlight_docid=atf" in href:
            # Extract docid e.g. atf://119-IV-309:fr
            m = re.search(r"highlight_docid=(atf://[^&]+)", href)
            if not m:
                continue
            docid = m.group(1)
            # Extract human reference e.g. "119 IV 309"
            ref_m = re.search(r"atf://(\d+-[IVX]+-\d+)", docid)
            ref = ref_m.group(1).replace("-", " ") if ref_m else docid
            full_url = urljoin("https://search.bger.ch", href)
            results.append({"ref": f"BGE {ref}", "docid": docid, "url": full_url})

    return results


def fetch_text(url: str, lang: str = "fr") -> str:
    """Fetch full text of an arrêt page."""
    # Try to get the language variant
    lang_url = re.sub(r"highlight_docid=atf://([^:]+):[a-z]+",
                      f"highlight_docid=atf://\\1:{lang}", url)
    try:
        resp = requests.get(lang_url, headers=HEADERS, timeout=15)
        resp.encoding = "iso-8859-1"
        soup = BeautifulSoup(resp.text, "html.parser")
        # Main text is usually in <div class="content"> or just the body paragraphs
        content = soup.find("div", class_="content") or soup.find("body")
        if content:
            text = content.get_text(separator="\n", strip=True)
            # Remove nav noise at top/bottom — keep from "Faits" or "Sachverhalt" onward
            for marker in ["Faits", "Sachverhalt", "Fatti", "Facts", "Regeste", "Erwägungen"]:
                idx = text.find(marker)
                if idx != -1:
                    text = text[idx:]
                    break
            return text.strip()
    except Exception as e:
        print(f"    Warning: could not fetch {lang_url}: {e}")
    return ""


def detect_language(ref: str, text_fr: str, text_de: str) -> str:
    """Guess original language from which language has more content."""
    if len(text_fr) > len(text_de) * 1.2:
        return "fr"
    elif len(text_de) > len(text_fr) * 1.2:
        return "de"
    return "fr"  # TF default


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape BGer arrêts into CSV")
    parser.add_argument("--keywords", nargs="+", default=DEFAULT_KEYWORDS)
    parser.add_argument("--from-year", type=int, default=2000)
    parser.add_argument("--to-year", type=int, default=2026)
    parser.add_argument("--output", default="bger_scraped.csv")
    parser.add_argument("--category", default="sexual",
                        help="Value for or_category column")
    args = parser.parse_args()

    fieldnames = [
        "prompt_id", "or_category", "bger_source", "bger_url",
        "task_fr", "task_hard_fr",
        "task_de", "task_hard_de",
        "task_it", "task_hard_it",
        "task_en", "task_hard_en",
        "orginal_language",
        "text_fr", "text_de", "text_it", "text_en",
    ]

    seen_refs = set()
    rows = []

    for keyword in args.keywords:
        print(f"\nSearching: «{keyword}»")
        results = search_keyword(keyword, args.from_year, args.to_year)
        print(f"  → {len(results)} results")

        for r in results:
            if r["ref"] in seen_refs:
                continue
            seen_refs.add(r["ref"])

            print(f"  Fetching {r['ref']} ...")
            text_fr = fetch_text(r["url"], "fr")
            time.sleep(0.8)
            text_de = fetch_text(r["url"], "de")
            time.sleep(0.8)
            text_it = fetch_text(r["url"], "it")
            time.sleep(0.8)

            orig_lang = detect_language(r["ref"], text_fr, text_de)
            idx = len(rows) + 1

            rows.append({
                "prompt_id":       f"bgr_{idx:02d}",
                "or_category":     args.category,
                "bger_source":     r["ref"],
                "bger_url":        r["url"],
                "task_fr":         TASK_FR,
                "task_hard_fr":    TASK_HARD_FR,
                "task_de":         TASK_DE,
                "task_hard_de":    TASK_HARD_DE,
                "task_it":         TASK_IT,
                "task_hard_it":    TASK_HARD_IT,
                "task_en":         TASK_EN,
                "task_hard_en":    TASK_HARD_EN,
                "orginal_language": orig_lang,
                "text_fr":         text_fr,
                "text_de":         text_de,
                "text_it":         text_it,
                "text_en":         "",   # fill later via translate_prompts.py
            })

    output_path = args.output
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✓ Saved {len(rows)} unique arrêts → {output_path}")


if __name__ == "__main__":
    main()
