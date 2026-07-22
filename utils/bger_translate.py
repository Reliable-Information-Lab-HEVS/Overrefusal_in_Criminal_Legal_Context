#!/usr/bin/env python3
"""
bger_translate.py — Traduction DeepL des colonnes text_* manquantes
TM François Brouchoud — dataset BGer élargi (200 arrêts)

Remplit les colonnes text_fr / text_de / text_it / text_en vides en traduisant
depuis la colonne de la langue d'origine (voir 'orginal_language'). Les tâches
task01_* sont déjà remplies dans le sample → non touchées.

Conçu pour un travail RÉPARTI et REPRENABLE :
  - saute toute cellule déjà remplie (donc plusieurs personnes peuvent lancer
    la même commande l'une après l'autre, chacune avec SA clé) ;
  - s'arrête proprement avant d'atteindre --max-chars (garde-fou du quota) ;
  - écrit le CSV après CHAQUE arrêt → une interruption ne perd rien.

⚠️ Chaque contributeur doit utiliser SON PROPRE compte DeepL (un compte Free
   par personne). Ne pas créer de comptes multiples ni masquer l'origine :
   c'est contraire aux CGU DeepL et non reproductible pour le rapport.
   Alternative plus propre : une clé DeepL Pro institutionnelle (HES-SO / TF).

Usage :
  pip install requests
  # créer un fichier .env à côté du script contenant :
  #   DEEPL_API_KEY=xxxxxxxx:fx        (:fx = clé Free ; sinon Pro)
  python bger_translate.py --in bger_extended_200.csv --out bger_extended_200.csv --max-chars 980000

  # relancer par la personne suivante (nouvelle clé dans SON .env) :
  # MÊME commande, reprend où ça s'est arrêté
"""

import argparse
import csv
import os
import sys
import time

import requests


def load_dotenv(path=".env"):
    """Charge les variables d'un fichier .env dans os.environ (sans écraser
    une variable déjà définie). Format : CLE=valeur, une par ligne ;
    lignes vides et commentaires (#) ignorés ; guillemets optionnels."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)

# langue de la colonne  ->  code cible DeepL
TARGET = {"fr": "FR", "de": "DE", "it": "IT", "en": "EN-GB"}
SOURCE = {"fr": "FR", "de": "DE", "it": "IT", "en": "EN"}
COLS = ["text_fr", "text_de", "text_it", "text_en"]
LANG_OF_COL = {"text_fr": "fr", "text_de": "de", "text_it": "it", "text_en": "en"}


def endpoint(key):
    return ("https://api-free.deepl.com/v2/translate"
            if key.strip().endswith(":fx")
            else "https://api.deepl.com/v2/translate")


def usage_url(key):
    return ("https://api-free.deepl.com/v2/usage"
            if key.strip().endswith(":fx")
            else "https://api.deepl.com/v2/usage")


def auth_headers(key):
    # Auth par en-tête, obligatoire depuis nov. 2025 (l'ancien auth_key en
    # corps de requête renvoie désormais 403).
    return {"Authorization": f"DeepL-Auth-Key {key}"}


def check_usage(key):
    try:
        r = requests.get(usage_url(key), headers=auth_headers(key), timeout=20)
        r.raise_for_status()
        d = r.json()
        used, limit = d.get("character_count", 0), d.get("character_limit", 0)
        return used, limit
    except Exception as e:
        print(f"[!] usage indisponible: {e}")
        return None, None


def translate(key, text, source_lang, target_lang, retries=4):
    for attempt in range(retries):
        try:
            r = requests.post(endpoint(key), timeout=60,
                headers=auth_headers(key),
                data={
                    "text": text,
                    "source_lang": source_lang, "target_lang": target_lang,
                    "preserve_formatting": "1", "split_sentences": "nonewlines",
                })
            if r.status_code == 456:
                sys.exit("[STOP] Quota DeepL épuisé pour cette clé (HTTP 456). "
                         "Au suivant, ou passe sur une clé Pro.")
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1)); continue
            r.raise_for_status()
            return r.json()["translations"][0]["text"]
        except requests.HTTPError:
            raise
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("échec traduction après retries")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--key", default=None,
                    help="clé DeepL (par défaut : DEEPL_API_KEY depuis .env ou l'environnement)")
    ap.add_argument("--env", default=".env", help="chemin du fichier .env (défaut : .env)")
    ap.add_argument("--max-chars", type=int, default=980000,
                    help="budget de caractères SOURCE envoyés (défaut 980000, marge sous 1M Free)")
    ap.add_argument("--sleep", type=float, default=0.5)
    args = ap.parse_args()

    env_had_key = "DEEPL_API_KEY" in os.environ
    load_dotenv(args.env)
    key = args.key or os.environ.get("DEEPL_API_KEY")
    if not key:
        sys.exit(f"Aucune clé trouvée. Mets DEEPL_API_KEY=... dans {args.env} "
                 f"(ou passe --key). Cherché dans : {os.path.abspath(args.env)}")
    key = key.strip()
    args.key = key

    # --- diagnostic clé ---
    if args.key:
        masked = (key[:4] + "…" + key[-3:]) if len(key) > 8 else "???"
        source = ("--key" if args.key and "--key" in sys.argv else
                  "variable d'environnement (prioritaire sur .env !)" if env_had_key else
                  f"fichier {os.path.abspath(args.env)}")
        print(f"[diag] clé utilisée : {masked} | longueur {len(key)} | "
              f"finit par ':fx' : {key.endswith(':fx')}")
        print(f"[diag] source : {source}")
        print(f"[diag] endpoint : {endpoint(key)}")

    used, limit = check_usage(args.key)
    if used is not None:
        print(f"[i] quota clé : {used:,} / {limit:,} caractères déjà consommés ce mois "
              f"({limit-used:,} restants)")

    with open(args.inp, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    orig_col = "orginal_language" if "orginal_language" in fields else "original_language"
    sent = 0
    done_cells = 0
    stopped = False

    for r in rows:
        lang = r[orig_col].strip()
        src_text = r.get(f"text_{lang}", "").strip()
        if not src_text:
            continue  # pas de texte source (ne devrait pas arriver)
        for col in COLS:
            tgt = LANG_OF_COL[col]
            if tgt == lang:
                continue                      # colonne d'origine
            if r.get(col, "").strip():
                continue                      # déjà traduit (reprise / autre contributeur)
            if sent + len(src_text) > args.max_chars:
                stopped = True
                break
            r[col] = translate(args.key, src_text, SOURCE[lang], TARGET[tgt])
            sent += len(src_text)
            done_cells += 1
            time.sleep(args.sleep)
        # écriture incrémentale après chaque arrêt
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
        if stopped:
            print(f"[STOP] budget --max-chars atteint ({sent:,} caractères envoyés).")
            break

    # bilan
    remaining = sum(
        1 for r in rows for col in COLS
        if LANG_OF_COL[col] != r[orig_col].strip()
        and r.get(f"text_{r[orig_col].strip()}", "").strip()
        and not r.get(col, "").strip()
    )
    print(f"[✓] {done_cells} cellules traduites, {sent:,} caractères source envoyés cette session.")
    print(f"[i] cellules encore vides dans le fichier : {remaining} "
          f"→ relancer avec la clé suivante (même commande).")


if __name__ == "__main__":
    main()