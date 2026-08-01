#!/usr/bin/env python3
"""
cedh_topup.py — Remplace les lignes « _A_REMPLACER » du dataset CEDH par des
affaires fraîches des mêmes catégories (l'équivalent de bger_topup.py).

Réutilise TEL QUEL le pipeline blindé de cedh_build_dataset.py : requêtes par
termes d'infraction + article Convention, extraction des circonstances,
reconstruction des §§ numérotés, VERIFY de contenu, appariement FR par appno
AVEC même kpdate, garde de concordance § par §. Exclut toutes les affaires
déjà présentes (appno + signature de texte). L'identifiant de la ligne
remplacée est conservé (cedh_063 reste cedh_063) — pas de renumérotation.

Usage (depuis ta machine, comme la collecte) :
  python cedh_topup.py --in data/cedh_dataset.csv --out data/cedh_dataset.csv
"""

import argparse
import csv
import re
import sys

from cedh_build_dataset import (
    QUERIES, VERIFY, search, fetch_text, extract_facts, find_pair,
    align_bilingual, first_appno, sig, BASE,
)

csv.field_size_limit(10**8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--min-facts", type=int, default=1000)
    ap.add_argument("--max-facts", type=int, default=12000)
    args = ap.parse_args()

    with open(args.inp, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames
        rows = list(rd)

    to_replace = [r for r in rows if "_A_REMPLACER" in r["prompt_id"]]
    if not to_replace:
        print("[i] aucune ligne _A_REMPLACER — rien à faire.")
        return
    need = {}
    for r in to_replace:
        need[r["category"]] = need.get(r["category"], 0) + 1
    print(f"[i] à remplacer : {need}")

    def appno_of(row):
        m = re.search(r"\(([\d/;+ ]+)\)\s*$", row["bger_source"])
        return m.group(1) if m else row["bger_source"]

    seen_app = {appno_of(r) for r in rows if "_A_REMPLACER" not in r["prompt_id"]}
    seen_sig = {sig(r["text_en"]) for r in rows if r["text_en"].strip()}

    fresh = {c: [] for c in need}
    for cat, n in need.items():
        q = QUERIES[cat]
        for term in q["en"]:
            if len(fresh[cat]) >= n:
                break
            for article in q["articles"]:
                if len(fresh[cat]) >= n:
                    break
                try:
                    _, res = search(cat, "ENG", term, article)
                except Exception as e:
                    print(f"[!] {cat}/{term}/{article}: {e}")
                    continue
                for c in res:
                    if len(fresh[cat]) >= n:
                        break
                    appno = first_appno(c)
                    itemid = c.get("itemid")
                    if not appno or not itemid or appno in seen_app:
                        continue
                    try:
                        facts_en = extract_facts(fetch_text(itemid))
                    except Exception:
                        continue
                    if not (args.min_facts <= len(facts_en) <= args.max_facts):
                        continue
                    if not VERIFY[cat].search(facts_en):
                        continue
                    s = sig(facts_en)
                    if s in seen_sig:
                        continue
                    facts_fr = ""
                    pair = find_pair(appno, "FRE", c.get("kpdate", ""))
                    if pair and pair.get("itemid"):
                        try:
                            ffr = extract_facts(fetch_text(pair["itemid"]))
                            if args.min_facts <= len(ffr) <= args.max_facts * 2:
                                facts_en, facts_fr = align_bilingual(facts_en, ffr)
                        except Exception:
                            pass
                    if len(facts_en) < args.min_facts or not VERIFY[cat].search(facts_en):
                        continue
                    seen_app.add(appno)
                    seen_sig.add(sig(facts_en))
                    fresh[cat].append((c, appno, itemid, facts_en, facts_fr))
                    both = "EN+FR" if facts_fr else "EN seul"
                    print(f"    + [{cat}] {c.get('docname','?')[:55]} ({both}, "
                          f"{len(facts_en)} c) [{len(fresh[cat])}/{n}]")

    replaced = 0
    for r in to_replace:
        pool = fresh.get(r["category"], [])
        if not pool:
            print(f"[!] pas de remplaçant pour {r['prompt_id']} — laissé marqué")
            continue
        c, appno, itemid, facts_en, facts_fr = pool.pop(0)
        keep_id = r["prompt_id"].replace("_A_REMPLACER", "")
        keep_cat = r["category"]
        keep_task = {k: r[k] for k in fields if k.startswith("task")}
        for k in fields:
            r[k] = ""
        r.update(keep_task)
        r["prompt_id"] = keep_id
        r["category"] = keep_cat
        r["bger_source"] = f"CEDH {c.get('docname','?')} ({appno})"
        r["bger_url"] = f"{BASE}/eng?i={itemid}"
        r["orginal_language"] = "en"
        r["text_en"], r["text_fr"] = facts_en, facts_fr
        replaced += 1
        print(f"[✓] {keep_id} <- {c.get('docname','?')[:60]}")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    left = [r["prompt_id"] for r in rows if "_A_REMPLACER" in r["prompt_id"]]
    print(f"\n[✓] {replaced} remplacement(s). Non résolus : {left or 'aucun'}")
    print(f"[✓] écrit : {args.out}")


if __name__ == "__main__":
    main()
