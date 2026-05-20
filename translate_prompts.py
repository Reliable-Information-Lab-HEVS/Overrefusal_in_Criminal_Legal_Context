

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import requests

# Load .env
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


PROJECT_ROOT = Path(__file__).resolve().parent

# The five category files with the shortest name (one per OR-Bench category).
DEFAULT_FILES = [
    PROJECT_ROOT / "data" / "orbench_harmful200.csv",
    PROJECT_ROOT / "data" / "orbench_illegal200.csv",
    PROJECT_ROOT / "data" / "orbench_sexual200.csv",
    PROJECT_ROOT / "data" / "orbench_unethical200.csv",
    PROJECT_ROOT / "data" / "orbench_violence200.csv",
]

# Column families translated when their source cell holds text.
FIELD_FAMILIES = ["text", "task", "task_hard"]

# All languages we keep columns for.
ALL_LANGS = ["fr", "de", "it", "en"]

# DeepL needs a regional variant for English as a *target* language.
DEEPL_TARGET = {"fr": "FR", "de": "DE", "it": "IT", "en": "EN-US"}
DEEPL_SOURCE = {"fr": "FR", "de": "DE", "it": "IT", "en": "EN"}

# DeepL allows up to 50 texts per request; stay a bit under.
BATCH_SIZE = 40


# Placeholders from .env.example that must never be treated as real keys.
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


class DeepLClient:
    """Thin DeepL wrapper with batch translation and key rotation."""

    def __init__(self, keys: list[str]):
        cleaned = [sanitize_key(k) for k in keys]
        self.keys = [
            k for k in cleaned if k and k.lower() not in _PLACEHOLDER_KEYS
        ]
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

            raise RuntimeError(
                f"DeepL error HTTP {resp.status_code}: {resp.text[:300]}"
            )


def translate_file(
    path: Path, client: DeepLClient | None, langs: list[str], dry_run: bool
) -> None:
    if not path.exists():
        print(f"[skip] {path.name}: file not found")
        return

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    # Collect every cell that needs translating, grouped by (source, target)
    # so identical strings in the same pair are sent once (cached).
    # jobs[(src, tgt)] = { source_text: [(row_index, target_col), ...] }
    jobs: dict[tuple[str, str], dict[str, list[tuple[int, str]]]] = {}

    for i, row in enumerate(rows):
        src_lang = (row.get("orginal_language") or "").strip().lower()
        if src_lang not in ALL_LANGS:
            continue
        for family in FIELD_FAMILIES:
            src_col = f"{family}_{src_lang}"
            if src_col not in fieldnames:
                continue
            src_text = (row.get(src_col) or "").strip()
            if not src_text:
                continue
            for tgt in langs:
                if tgt == src_lang:
                    continue
                tgt_col = f"{family}_{tgt}"
                if tgt_col not in fieldnames:
                    continue
                if (row.get(tgt_col) or "").strip():
                    continue  # already translated -> resumable
                jobs.setdefault((src_lang, tgt), {}).setdefault(src_text, []).append(
                    (i, tgt_col)
                )

    total_cells = sum(
        len(targets) for pair in jobs.values() for targets in pair.values()
    )
    total_calls = sum(len(pair) for pair in jobs.values())
    print(
        f"[{path.name}] {total_cells} cells to fill "
        f"({total_calls} unique strings) across {len(jobs)} language pairs"
    )

    if dry_run or total_cells == 0:
        return

    assert client is not None
    done = 0
    for (src_lang, tgt), text_map in jobs.items():
        uniques = list(text_map.keys())
        for start in range(0, len(uniques), BATCH_SIZE):
            batch = uniques[start : start + BATCH_SIZE]
            translations = client.translate(batch, src_lang, tgt)
            for src_text, translated in zip(batch, translations):
                for row_idx, col in text_map[src_text]:
                    rows[row_idx][col] = translated
                    done += 1

            _write_csv(path, fieldnames, rows)
            print(f"  {src_lang}->{tgt}: {done}/{total_cells} cells written")

    print(f"[{path.name}] done.")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)  # atomic on the same filesystem


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate prompt CSVs via DeepL.")
    parser.add_argument(
        "--files",
        nargs="+",
        type=Path,
        default=DEFAULT_FILES,
        help="CSV files to translate (default: the five orbench *200.csv files).",
    )
    parser.add_argument(
        "--langs",
        nargs="+",
        default=["fr", "de", "it"],
        choices=ALL_LANGS,
        help="Target languages (default: fr de it).",
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
        translate_file(Path(path), client, args.langs, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
