#!/usr/bin/env python3
"""Translate the <family>_<lang> columns of a prompt CSV via the DeepL API.

Generic CSV translator for the canonical input schema (see
data/INPUT_FORMAT.md). It auto-detects every translatable column family in the
header -- any column named ``<family>_<lang>`` with a supported language code
(fr/de/it/en) -- so ``text_*``, ``task01_*``, ``task02_*`` ... are all handled
without editing this file.

For each row, the source language is read from the ``orginal_language`` column
(or forced with ``--source-lang``); every non-empty source cell is translated
into the requested target languages, skipping cells that are already filled (so
the run is resumable). The CSV is rewritten in place after each batch.

Usage:
    # fill the DE/IT/EN cells of one file from its FR cells
    python helpers/translate_prompts.py --files data/tf_cases.csv --langs de it en

    # force the source language when the CSV has no orginal_language column
    python helpers/translate_prompts.py --files data/tf_cases.csv \
        --source-lang fr --langs de it en

    # see what would be translated without calling the API
    python helpers/translate_prompts.py --files data/tf_cases.csv --langs de it en --dry-run

Set DEEPL_API_KEY in your environment or a .env file (one or more keys,
comma-separated; free keys end with ':fx'), or pass --keys.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import requests


def _load_env() -> None:
    """Load a .env if python-dotenv is available, searching upward from the cwd
    so it works regardless of where this script sits in the tree."""
    try:
        from dotenv import find_dotenv, load_dotenv  # type: ignore
    except ImportError:
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path)


_load_env()


# Supported language codes. Keep in sync with the pipeline
# (over_refusal/config.py SUPPORTED_LANGUAGES).
ALL_LANGS = ["fr", "de", "it", "en"]

# DeepL needs a regional variant for English as a *target* language.
DEEPL_TARGET = {"fr": "FR", "de": "DE", "it": "IT", "en": "EN-US"}
DEEPL_SOURCE = {"fr": "FR", "de": "DE", "it": "IT", "en": "EN"}

# DeepL allows up to 50 texts per request; stay a bit under.
BATCH_SIZE = 40

# Placeholders that must never be treated as real keys.
_PLACEHOLDER_KEYS = {"key1", "key2", "key1:fx", "your-deepl-key-here"}


def sanitize_key(key: str) -> str:
    """Trim whitespace and a stray trailing ':' (e.g. '<uuid>:fx:' -> '<uuid>:fx')."""
    return key.strip().rstrip(":")


def endpoint_for_key(key: str) -> str:
    """Free DeepL keys end in ':fx' and use a different host."""
    return (
        "https://api-free.deepl.com/v2/translate"
        if key.endswith(":fx")
        else "https://api.deepl.com/v2/translate"
    )


def discover_families(fieldnames: list[str], langs: list[str]) -> list[str]:
    """Infer translatable column families from the header.

    A *family* is any prefix ``P`` such that a column ``P_<lang>`` exists for at
    least one ``lang`` in ``langs``. This keeps the tool schema-agnostic:
    ``text_*``, ``task01_*``, ``task02_*`` ... are discovered automatically,
    with no hard-coded column list to keep in sync.
    """
    suffixes = {f"_{l}": len(l) + 1 for l in langs}
    families: set[str] = set()
    for col in fieldnames:
        for suf, n in suffixes.items():
            if col.endswith(suf):
                families.add(col[:-n])
                break
    return sorted(families)


class DeepLClient:
    """Thin DeepL wrapper with batch translation and key rotation."""

    def __init__(self, keys: list[str]):
        cleaned = [sanitize_key(k) for k in keys]
        self.keys = [k for k in cleaned if k and k.lower() not in _PLACEHOLDER_KEYS]
        if not self.keys:
            raise ValueError(
                "No usable DeepL API key. Set DEEPL_API_KEY in .env or pass --keys."
            )
        self.idx = 0
        self.session = requests.Session()

    @property
    def _key(self) -> str:
        return self.keys[self.idx]

    def _rotate(self) -> bool:
        """Move to the next key. Returns False if none are left."""
        if self.idx + 1 < len(self.keys):
            self.idx += 1
            print(f"  [key] quota reached, switching to key #{self.idx + 1}")
            return True
        return False

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        """Translate a batch of texts. Retries on transient errors / rotates on quota."""
        attempt = 0
        while True:
            attempt += 1
            key = self._key
            resp = self.session.post(
                endpoint_for_key(key),
                headers={"Authorization": f"DeepL-Auth-Key {key}"},
                data=[
                    ("source_lang", DEEPL_SOURCE[source]),
                    ("target_lang", DEEPL_TARGET[target]),
                    *[("text", t) for t in texts],
                ],
                timeout=60,
            )

            if resp.status_code == 200:
                return [t["text"] for t in resp.json()["translations"]]

            # 456 = quota exceeded for this key.
            if resp.status_code == 456:
                if self._rotate():
                    continue
                raise RuntimeError("All DeepL keys have exhausted their quota (456).")

            # 429 / 5xx = transient, back off and retry (a few times).
            if resp.status_code in (429, 500, 502, 503, 529) and attempt <= 5:
                wait = min(2 ** attempt, 30)
                print(f"  [retry] HTTP {resp.status_code}, waiting {wait}s")
                time.sleep(wait)
                continue

            raise RuntimeError(f"DeepL error HTTP {resp.status_code}: {resp.text[:300]}")


def translate_file(
    path: Path,
    client: DeepLClient | None,
    langs: list[str],
    dry_run: bool,
    source_lang: str | None = None,
) -> None:
    if not path.exists():
        print(f"[skip] {path.name}: file not found")
        return

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    families = discover_families(fieldnames, ALL_LANGS)
    if not families:
        print(f"[skip] {path.name}: no <family>_<lang> columns to translate")
        return

    # Collect every cell that needs translating, grouped by (source, target)
    # so identical strings in the same pair are sent once (cached).
    # jobs[(src, tgt)] = { source_text: [(row_index, target_col), ...] }
    jobs: dict[tuple[str, str], dict[str, list[tuple[int, str]]]] = {}

    for i, row in enumerate(rows):
        src = source_lang or (row.get("orginal_language") or "").strip().lower()
        if src not in ALL_LANGS:
            continue
        for family in families:
            src_col = f"{family}_{src}"
            if src_col not in fieldnames:
                continue
            src_text = (row.get(src_col) or "").strip()
            if not src_text:
                continue
            for tgt in langs:
                if tgt == src:
                    continue
                tgt_col = f"{family}_{tgt}"
                if tgt_col not in fieldnames:
                    continue
                if (row.get(tgt_col) or "").strip():
                    continue  # already translated -> resumable
                jobs.setdefault((src, tgt), {}).setdefault(src_text, []).append(
                    (i, tgt_col)
                )

    total_cells = sum(len(t) for pair in jobs.values() for t in pair.values())
    total_calls = sum(len(pair) for pair in jobs.values())
    print(
        f"[{path.name}] families={families} -> {total_cells} cells to fill "
        f"({total_calls} unique strings) across {len(jobs)} language pairs"
    )

    if dry_run or total_cells == 0:
        return

    assert client is not None
    done = 0
    for (src, tgt), text_map in jobs.items():
        uniques = list(text_map.keys())
        for start in range(0, len(uniques), BATCH_SIZE):
            batch = uniques[start : start + BATCH_SIZE]
            translations = client.translate(batch, src, tgt)
            for src_text, translated in zip(batch, translations):
                for row_idx, col in text_map[src_text]:
                    rows[row_idx][col] = translated
                    done += 1
            _write_csv(path, fieldnames, rows)
            print(f"  {src}->{tgt}: {done}/{total_cells} cells written")

    print(f"[{path.name}] done.")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)  # atomic on the same filesystem


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Translate the <family>_<lang> columns of prompt CSV(s) via DeepL."
    )
    parser.add_argument(
        "--files",
        nargs="+",
        type=Path,
        required=True,
        help="CSV file(s) to translate (canonical schema, see data/INPUT_FORMAT.md).",
    )
    parser.add_argument(
        "--langs",
        nargs="+",
        default=["fr", "de", "it", "en"],
        choices=ALL_LANGS,
        help="Target languages to fill (default: fr de it en).",
    )
    parser.add_argument(
        "--source-lang",
        default=None,
        choices=ALL_LANGS,
        help="Force the source language for every row (overrides the "
             "orginal_language column; useful when that column is absent).",
    )
    parser.add_argument(
        "--keys",
        default="",
        help="Comma-separated DeepL keys (overrides DEEPL_API_KEY).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be translated without calling the API.",
    )
    args = parser.parse_args()

    raw_keys = args.keys or os.environ.get("DEEPL_API_KEY", "")
    keys = raw_keys.split(",")

    client: DeepLClient | None = None
    if not args.dry_run:
        try:
            client = DeepLClient(keys)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Using {len(client.keys)} DeepL key(s).")

    for path in args.files:
        translate_file(Path(path), client, args.langs, args.dry_run, args.source_lang)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())