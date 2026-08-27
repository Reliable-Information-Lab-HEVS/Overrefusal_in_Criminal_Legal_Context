#!/usr/bin/env python3
"""Fill the empty text_fr / text_de / text_it / text_en columns with DeepL.

Each judgment is translated from its own source language (column
`orginal_language`) into the other three. Resumable: cells that already hold
text are skipped, a character budget stops the run before the free-tier quota,
and the file is rewritten after every judgment so an interrupted run loses
nothing.

The API key is read from DEEPL_API_KEY (environment or a local .env, never
committed). See .env.example.

  python helpers/bger_translate.py --in data/bger_full200.csv --out data/bger_full200.csv
"""
import argparse
import csv
import os
import sys
import time

import requests

csv.field_size_limit(10**8)

# column language -> DeepL target / source code
TARGET = {"fr": "FR", "de": "DE", "it": "IT", "en": "EN-GB"}
SOURCE = {"fr": "FR", "de": "DE", "it": "IT", "en": "EN"}
LANGS = ["fr", "de", "it", "en"]

# HTTP codes worth retrying: timeouts and overload, not quota or auth errors.
TRANSIENT = {408, 429, 500, 502, 503, 504, 529}


def load_dotenv(path=".env"):
    """Read KEY=value lines into os.environ without overwriting what is set."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api_base(key):
    """Free keys end in ':fx' and use a different host."""
    return "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"


def auth_headers(key):
    # Header auth is mandatory since Nov. 2025; auth_key in the body returns 403.
    return {"Authorization": f"DeepL-Auth-Key {key}"}


def check_usage(key):
    try:
        r = requests.get(f"{api_base(key)}/v2/usage", headers=auth_headers(key), timeout=20)
        r.raise_for_status()
        data = r.json()
        return data.get("character_count", 0), data.get("character_limit", 0)
    except Exception as exc:
        print(f"[!] usage unavailable: {exc}")
        return None, None


def translate(key, text, source_lang, target_lang, retries=6):
    for attempt in range(retries):
        try:
            r = requests.post(f"{api_base(key)}/v2/translate", timeout=120,
                              headers=auth_headers(key),
                              data={"text": text,
                                    "source_lang": source_lang,
                                    "target_lang": target_lang,
                                    "preserve_formatting": "1",
                                    "split_sentences": "nonewlines"})
            if r.status_code == 456:
                sys.exit("[stop] DeepL quota exhausted for this key (HTTP 456).")
            if r.status_code in TRANSIENT:
                wait = min(30, 3 * (attempt + 1))
                print(f"    [retry] HTTP {r.status_code} in {wait}s "
                      f"({attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()["translations"][0]["text"]
        except (requests.Timeout, requests.ConnectionError) as exc:
            wait = min(30, 3 * (attempt + 1))
            print(f"    [retry] {type(exc).__name__} in {wait}s ({attempt + 1}/{retries})")
            time.sleep(wait)
    raise RuntimeError(f"translation failed after {retries} attempts")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--env", default=".env", help="path to the .env file")
    ap.add_argument("--max-chars", type=int, default=980_000,
                    help="budget of SOURCE characters to send (default: just "
                         "under the 1M free-tier monthly quota)")
    ap.add_argument("--sleep", type=float, default=0.5)
    args = ap.parse_args()

    load_dotenv(args.env)
    key = (os.environ.get("DEEPL_API_KEY") or "").strip()
    if not key:
        sys.exit(f"No key found. Set DEEPL_API_KEY in {os.path.abspath(args.env)}.")

    used, limit = check_usage(key)
    if used is not None:
        print(f"[i] key quota: {used:,} / {limit:,} characters used this month")

    with open(args.inp, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    sent, translated, stopped = 0, 0, False
    for row in rows:
        source = row["orginal_language"].strip()
        text = row.get(f"text_{source}", "").strip()
        if not text:
            continue
        for lang in LANGS:
            if lang == source or row.get(f"text_{lang}", "").strip():
                continue                              # source column, or already done
            if sent + len(text) > args.max_chars:
                stopped = True
                break
            row[f"text_{lang}"] = translate(key, text, SOURCE[source], TARGET[lang])
            sent += len(text)
            translated += 1
            time.sleep(args.sleep)
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        if stopped:
            print(f"[stop] --max-chars reached ({sent:,} characters sent).")
            break

    remaining = sum(1 for row in rows for lang in LANGS
                    if lang != row["orginal_language"].strip()
                    and row.get(f"text_{row['orginal_language'].strip()}", "").strip()
                    and not row.get(f"text_{lang}", "").strip())
    print(f"[ok] {translated} cells translated, {sent:,} source characters sent.")
    print(f"[i] cells still empty: {remaining} (rerun with another key to finish)")


if __name__ == "__main__":
    main()
