#!/usr/bin/env python3
"""Merge all scattered result CSVs into ONE canonical long-format master.

The results were produced in several batches with inconsistent schemas: the
English files encode the prefix in a ``condition`` column (none/lawyer/supreme/
jailbreak), while the French/German files encode it in ``task_variant``
(normal = no prefix, hard = supreme-court). This script normalizes both into a
single ``prefix`` column and writes ``results/master_long.csv`` — one row per
(model, lang, topic, prefix, prompt_id), which every figure/table script can
then read from.

Run from the repo root:  python helpers/unify.py
"""
import csv
import glob
import os
from collections import defaultdict

TOPICS = ["violence", "sexual", "harmful", "unethical", "illegal"]

# Canonical prefix names.
PREFIXES = ["none", "lawyer", "supreme-court", "jailbreak"]

# English files use a `condition` column whose values are already canonical
# (none / lawyer / supreme-court / jailbreak).
CONDITION_TO_PREFIX = {p: p for p in PREFIXES}

# French/German files use task_variant; normal = no prefix, hard = supreme-court.
VARIANT_TO_PREFIX = {"normal": "none", "hard": "supreme-court"}

FIELDS = ["model", "lang", "topic", "prefix", "prompt_id",
          "is_refused", "is_error", "response_preview"]


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def _base_prompt_id(pid: str) -> str:
    """Strip any prefix-variant suffix so the id is comparable across files."""
    for s in ("_prefix", "_p2_lawyer", "_p3_jailbreak", "_supreme-court",
              "_lawyer", "_jailbreak"):
        pid = pid.replace(s, "")
    return pid


def _prefix_for(row: dict) -> str | None:
    """Resolve the canonical prefix from whichever column the file uses."""
    if row.get("prefix"):                       # new-style files (--prefix)
        return row["prefix"] if row["prefix"] in PREFIXES else None
    if row.get("condition"):                    # English *_all.csv
        return CONDITION_TO_PREFIX.get(row["condition"].strip())
    if row.get("task_variant"):                 # French/German *_frde_all.csv
        return VARIANT_TO_PREFIX.get(row["task_variant"].strip())
    return None


def _topic_from_path(path: str) -> str | None:
    for t in TOPICS:
        if f"_{t}200" in path or f"orbench_{t}" in path:
            return t
    return None


def load_file(path: str) -> list[dict]:
    out = []
    topic = _topic_from_path(path)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        prefix = _prefix_for(r)
        if prefix is None:
            continue
        out.append({
            "model": r.get("model", "").strip(),
            "lang": r.get("lang", "").strip(),
            "topic": r.get("category", "").strip() or topic or "",
            "prefix": prefix,
            "prompt_id": _base_prompt_id(r.get("prompt_id", "").strip()),
            "is_refused": _truthy(r.get("is_refused")),
            "is_error": _truthy(r.get("is_error")),
            "response_preview": r.get("response_preview", ""),
        })
    return out


def main() -> None:
    sources = sorted(
        glob.glob("results/english/*.csv")
        + glob.glob("results/french_german/*_frde_all.csv")
    )
    rows: list[dict] = []
    for path in sources:
        n = len(rows)
        rows += load_file(path)
        print(f"  + {path}  ({len(rows) - n} rows)")

    if not rows:
        print("No input rows found. Check results/ paths.")
        return

    os.makedirs("results", exist_ok=True)
    with open("results/master_long.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote results/master_long.csv ({len(rows)} rows)")

    # Quick sanity summary: refused/total per (model, lang, topic, prefix)
    counts = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["is_error"]:
            continue
        k = (r["model"], r["lang"], r["topic"], r["prefix"])
        counts[k][1] += 1
        counts[k][0] += int(r["is_refused"])
    langs = sorted({k[1] for k in counts})
    print(f"\nCoverage: {len(counts)} (model,lang,topic,prefix) cells "
          f"across langs={langs}")


if __name__ == "__main__":
    main()
