"""Fill missing translations with DeepL.

Two kinds of files are completed:

  * Data CSVs (prompts.py format): for each row, the text written in
    `orginal_language` is translated into the other target languages whenever
    the `text_<lang>` cell is still empty.

  * Task JSON files (prompts/<name>.json): the source `task_<lang>` (English by
    default) is translated into the other target `task_<lang>` keys when empty.

Already-filled cells are never overwritten, so runs are resumable. Run with
`--dry-run` first to see how many cells would be filled without spending quota.

    python -m refusal_eval.translate --data data/*.csv --tasks
    python -m refusal_eval.translate --data data/orbench_harmful.csv --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Optional

import requests

from refusal_eval.config import PROMPTS_DIR, get_deepl_keys

ALL_LANGS = ["fr", "de", "en"]
DEEPL_TARGET = {"fr": "FR", "de": "DE", "en": "EN-US"}
DEEPL_SOURCE = {"fr": "FR", "de": "DE", "en": "EN"}
BATCH_SIZE = 40

_PLACEHOLDER_KEYS = {"key1", "key2", "key1:fx", "your-deepl-key-here", "your_deepl_key_here"}


def _sanitize_key(key: str) -> str:
    return key.strip().rstrip(":")


def _endpoint_for_key(key: str) -> str:
    return ("https://api-free.deepl.com/v2/translate"
            if key.endswith(":fx")
            else "https://api.deepl.com/v2/translate")


class DeepLClient:
    """Thin DeepL wrapper with batch translation and key rotation on quota."""

    def __init__(self, keys: list[str]):
        cleaned = [_sanitize_key(k) for k in keys]
        self.keys = [k for k in cleaned if k and k.lower() not in _PLACEHOLDER_KEYS]
        if not self.keys:
            raise ValueError("No usable DeepL key. Set DEEPL_API_KEY in .env or pass --keys.")
        self.idx = 0
        self.session = requests.Session()

    @property
    def _key(self) -> str:
        return self.keys[self.idx]

    def _rotate(self) -> bool:
        if self.idx + 1 < len(self.keys):
            self.idx += 1
            print(f"  [key] quota reached, switching to key #{self.idx + 1}")
            return True
        return False

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        attempt = 0
        while True:
            attempt += 1
            key = self._key
            resp = self.session.post(
                _endpoint_for_key(key),
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
            if resp.status_code == 456:  # quota exhausted for this key
                if self._rotate():
                    continue
                raise RuntimeError("All DeepL keys have exhausted their quota (456).")
            if resp.status_code in (429, 500, 502, 503, 529) and attempt <= 5:
                wait = min(2 ** attempt, 30)
                print(f"  [retry] HTTP {resp.status_code}, waiting {wait}s")
                time.sleep(wait)
                continue
            raise RuntimeError(f"DeepL error HTTP {resp.status_code}: {resp.text[:300]}")


def _translate_pairs(
    client: DeepLClient, pairs: dict[tuple[str, str], dict[str, list]]
) -> int:
    """Translate grouped jobs and apply them via the stored setters.

    `pairs[(src, tgt)] = { source_text: [setter, ...] }` where each setter is a
    callable taking the translated string.
    """
    done = 0
    for (src, tgt), text_map in pairs.items():
        uniques = list(text_map.keys())
        for start in range(0, len(uniques), BATCH_SIZE):
            batch = uniques[start:start + BATCH_SIZE]
            translations = client.translate(batch, src, tgt)
            for src_text, translated in zip(batch, translations):
                for setter in text_map[src_text]:
                    setter(translated)
                    done += 1
    return done


def translate_data_file(
    path: Path, client: Optional[DeepLClient], langs: list[str], dry_run: bool
) -> None:
    if not path.exists():
        print(f"[skip] {path.name}: not found")
        return

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    pairs: dict[tuple[str, str], dict[str, list]] = {}
    for row in rows:
        src = (row.get("orginal_language") or "").strip().lower()
        if src not in ALL_LANGS:
            continue
        src_text = (row.get(f"text_{src}") or "").strip()
        if not src_text:
            continue
        for tgt in langs:
            if tgt == src or f"text_{tgt}" not in fieldnames:
                continue
            if (row.get(f"text_{tgt}") or "").strip():
                continue
            r, col = row, f"text_{tgt}"
            pairs.setdefault((src, tgt), {}).setdefault(src_text, []).append(
                lambda v, r=r, col=col: r.__setitem__(col, v)
            )

    cells = sum(len(s) for m in pairs.values() for s in m.values())
    print(f"[{path.name}] {cells} cells to fill across {len(pairs)} language pairs")
    if dry_run or cells == 0:
        return

    assert client is not None
    _translate_pairs(client, pairs)
    _write_csv(path, fieldnames, rows)
    print(f"[{path.name}] done.")


def translate_task_file(
    path: Path, client: Optional[DeepLClient], langs: list[str], dry_run: bool
) -> None:
    if not path.exists():
        print(f"[skip] {path.name}: not found")
        return

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Source = English if present, else the first non-empty task_<lang>.
    src = None
    if (data.get("task_en") or "").strip():
        src = "en"
    else:
        for lang in ALL_LANGS:
            if (data.get(f"task_{lang}") or "").strip():
                src = lang
                break
    if src is None:
        print(f"[skip] {path.name}: no source text")
        return

    src_text = data[f"task_{src}"].strip()
    pairs: dict[tuple[str, str], dict[str, list]] = {}
    for tgt in langs:
        if tgt == src:
            continue
        if (data.get(f"task_{tgt}") or "").strip():
            continue
        col = f"task_{tgt}"
        pairs.setdefault((src, tgt), {}).setdefault(src_text, []).append(
            lambda v, col=col: data.__setitem__(col, v)
        )

    cells = sum(len(s) for m in pairs.values() for s in m.values())
    print(f"[{path.name}] {cells} task translation(s) to fill (source={src})")
    if dry_run or cells == 0:
        return

    assert client is not None
    _translate_pairs(client, pairs)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[{path.name}] done.")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)  # atomic on the same filesystem


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill missing translations via DeepL.")
    parser.add_argument("--data", nargs="*", type=Path, default=[],
                        help="Data CSV files to complete.")
    parser.add_argument("--tasks", action="store_true",
                        help="Also complete every task JSON in the prompts/ folder.")
    parser.add_argument("--task-files", nargs="*", type=Path, default=[],
                        help="Specific task JSON files to complete.")
    parser.add_argument("--langs", nargs="+", default=["fr", "de"], choices=ALL_LANGS,
                        help="Target languages (default: fr de).")
    parser.add_argument("--keys", default="", help="Comma-separated DeepL keys (overrides env).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be translated without calling the API.")
    args = parser.parse_args()

    task_files = list(args.task_files)
    if args.tasks:
        task_files += sorted(Path(PROMPTS_DIR).glob("*.json"))

    if not args.data and not task_files:
        print("Nothing to do: pass --data, --tasks, or --task-files.", file=sys.stderr)
        return 1

    client: Optional[DeepLClient] = None
    if not args.dry_run:
        keys = (args.keys or get_deepl_keys()).split(",")
        try:
            client = DeepLClient(keys)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Using {len(client.keys)} DeepL key(s).")

    for path in args.data:
        translate_data_file(Path(path), client, args.langs, args.dry_run)
    for path in task_files:
        translate_task_file(Path(path), client, args.langs, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
