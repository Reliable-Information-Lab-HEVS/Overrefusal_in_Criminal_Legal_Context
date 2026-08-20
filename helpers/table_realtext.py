#!/usr/bin/env python3
"""Print the real-text table (paper Table 3) from the BGer paragraph runs.

Refusal rate (%) per model, language and prefix condition, over the 1,652
paragraphs of the 192 aligned judgments. Italian is available for Llama and
Apertus only, so the pooled column uses en/fr/de like the paper.

Run from the repo root:  python helpers/table_realtext.py
"""
import csv
import glob
import os
from collections import defaultdict

csv.field_size_limit(10**8)

LANGS = ["en", "fr", "de"]
PREFIXES = ["none", "supreme-court"]
ORDER = ["llama3.1-8b", "gemma4-e4b", "apertus-8b", "qwen3-8b"]


def rates(rows, drop_empty=False):
    """(lang, prefix) -> refusal rate in %, plus the pooled 'all' key."""
    counts = defaultdict(lambda: [0, 0])
    for r in rows:
        if drop_empty and r["is_empty"] == "True":
            continue
        for key in ((r["lang"], r["prefix"]), ("all", r["prefix"])):
            counts[key][1] += 1
            counts[key][0] += r["is_refused"] == "True"
    return {k: 100 * n / t for k, (n, t) in counts.items() if t}


def main() -> None:
    files = {os.path.basename(p)[:-4]: p
             for p in glob.glob("results/real_text/bger_para/*.csv")}
    header = "".join(f"{l:>14}" for l in LANGS + ["total"])
    print(f"{'model':<14}{header}     (none / supreme-court)")

    for slug in [s for s in ORDER if s in files] + sorted(set(files) - set(ORDER)):
        rows = [r for r in csv.DictReader(open(files[slug], encoding="utf-8"))
                if r["lang"] in LANGS]
        r_all = rates(rows)
        cells = "".join(f"{r_all[(l, 'none')]:>7.1f} /{r_all[(l, 'supreme-court')]:>5.1f}"
                        for l in LANGS + ["all"])
        print(f"{slug:<14}{cells}")

        # Apertus returns strictly empty responses; report the rate without them.
        if any(r["is_empty"] == "True" for r in rows):
            r_ne = rates(rows, drop_empty=True)
            cells = "".join(f"{r_ne[(l, 'none')]:>7.1f} /{r_ne[(l, 'supreme-court')]:>5.1f}"
                            for l in LANGS + ["all"])
            print(f"{'  (non-empty)':<14}{cells}")


if __name__ == "__main__":
    main()
