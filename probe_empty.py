#!/usr/bin/env python3
"""
probe_empty.py — Diagnostic des réponses VIDES d'un run.

Certaines clés (prompt_id, langue) ressortent avec une réponse vide : Ollama
répond bien 200, mais le champ "response" est vide. Ce n'est pas une erreur
réseau — donc `run_tf.py` ne les marque pas is_error, et à temperature 0 le vide
est en général REPRODUCTIBLE : le run les retente indéfiniment sans jamais les
remplir.

Ce script rejoue ces prompts et affiche ce que dit Ollama sous le capot :

  done_reason        pourquoi la génération s'est arrêtée
                     "stop"   = le modèle a décidé d'arrêter (vide = choix du modèle)
                     "length" = plafond de sortie atteint
                     "load"   = rechargement du modèle, réponse vide parasite
  prompt_eval_count  nb de tokens du prompt RÉELLEMENT vus par le modèle
                     -> s'il plafonne à num_ctx, le prompt a été TRONQUÉ
  eval_count         nb de tokens générés (0 = rien produit)

Le point clé : Ollama tronque par la GAUCHE quand le prompt dépasse num_ctx.
Comme la consigne est au DÉBUT du prompt (task + "\\n\\n" + texte de l'arrêt),
un dépassement fait disparaître la consigne et il ne reste qu'un bloc de texte
brut — sur quoi le modèle n'a plus rien à faire, et sort du vide. `--num-ctx`
teste directement cette hypothèse.

Exemples :
  # rejouer les 10 premiers trous, réglages identiques au run
  python probe_empty.py --results results/tf_2cond_apertus.csv \\
      --prompts-file data/bger_dataset.csv \\
      --model "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M" --limit 10

  # même chose avec une fenêtre de contexte élargie -> si ça se remplit,
  # c'était une troncature, pas un comportement du modèle
  python probe_empty.py --results results/tf_2cond_apertus.csv \\
      --prompts-file data/bger_dataset.csv \\
      --model "hf.co/..." --limit 10 --num-ctx 16384

  # inventaire seul, sans appeler le modèle
  python probe_empty.py --results results/tf_2cond_apertus.csv \\
      --prompts-file data/bger_dataset.csv --list-only
"""
import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict

import requests

csv.field_size_limit(10 ** 8)

OLLAMA_URL = "http://localhost:11434/api/generate"


def build_prompt(ds_row, variant, lang):
    """Reconstruit le prompt EXACTEMENT comme over_refusal.prompts._build_prompt_text."""
    task = (ds_row.get(f"{variant}_{lang}") or "").strip()
    text = (ds_row.get(f"text_{lang}") or "").strip()
    if not text:
        return task
    if not task:
        return text
    return f"{task}\n\n{text}"


def find_holes(results_path):
    """Clés sans aucune réponse non vide, + nb de tentatives déjà faites."""
    rows = list(csv.DictReader(open(results_path, newline="", encoding="utf-8")))
    by = defaultdict(list)
    for r in rows:
        by[(r["prompt_id"], r["lang"], r["model"])].append(r)
    holes = {}
    for k, v in by.items():
        if not any((x.get("response_full") or "").strip() for x in v):
            holes[k] = len(v)
    return holes, len(by), len(rows)


def main():
    ap = argparse.ArgumentParser(description="Diagnostic des réponses vides d'un run.")
    ap.add_argument("--results", required=True, help="CSV de résultats (sortie run_tf.py)")
    ap.add_argument("--prompts-file", required=True, help="dataset source (data/bger_dataset.csv)")
    ap.add_argument("--model", default=None,
                    help="nom Ollama du modèle (défaut : celui trouvé dans le CSV)")
    ap.add_argument("--ollama-url", default=OLLAMA_URL)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--limit", type=int, default=10, help="nb de trous à rejouer (défaut 10)")
    ap.add_argument("--num-ctx", type=int, default=None,
                    help="force la fenêtre de contexte (teste l'hypothèse troncature)")
    ap.add_argument("--num-predict", type=int, default=None, help="plafond de tokens générés")
    ap.add_argument("--list-only", action="store_true", help="inventaire seul, aucun appel")
    args = ap.parse_args()

    holes, n_keys, n_rows = find_holes(args.results)
    ds = {r["prompt_id"]: r for r in csv.DictReader(
        open(args.prompts_file, newline="", encoding="utf-8"))}

    # --- contrôle de complétude : la grille attendue est-elle couverte ? -------
    # Un trou peut avoir DEUX causes très différentes : la clé a été appelée et
    # le modèle n'a rien renvoyé, ou la clé n'a JAMAIS été appelée (run coupé).
    # Compter les lignes du CSV ne les distingue pas — une même clé peut y
    # figurer 3 fois. On compare donc au produit dataset x conditions x langues.
    langs = sorted({k[1] for k in
                    {(r["prompt_id"], r["lang"]) for r in
                     csv.DictReader(open(args.results, newline="", encoding="utf-8"))}})
    variants = sorted({r["task_variant"] for r in
                       csv.DictReader(open(args.results, newline="", encoding="utf-8"))
                       if r.get("task_variant")})
    attempted = {(r["prompt_id"], r["lang"]) for r in
                 csv.DictReader(open(args.results, newline="", encoding="utf-8"))}
    multi = any("__" in pid for pid, _ in attempted)
    grid = {(f"{p}__{v}" if multi else p, l)
            for p in ds for v in (variants or ["task01"]) for l in langs}
    never = grid - attempted

    print(f"[i] {args.results}")
    print(f"    {n_rows} lignes -> {n_keys} clés uniques "
          f"(une clé peut avoir plusieurs tentatives : ne compte pas les lignes)")
    print(f"    grille attendue : {len(ds)} arrêts x {len(variants) or 1} condition(s) "
          f"x {len(langs)} langue(s) = {len(grid)}")
    print(f"    jamais appelées : {len(never)}")
    print(f"    appelées mais réponse vide : {len(holes)}")
    print(f"    exploitables : {len(grid) - len(never) - len(holes)}")
    if never:
        print(f"    /!\\ {len(never)} clé(s) n'ont JAMAIS été appelées -> relancer run_tf.py")
        print("        par langue :", dict(Counter(k[1] for k in never)))
    if not holes:
        print("[✓] aucune réponse vide à diagnostiquer.")
        return

    print(f"    tentatives déjà faites par trou : {dict(Counter(holes.values()))}")
    print(f"    par langue    : {dict(Counter(k[1] for k in holes))}")
    print(f"    par condition : {dict(Counter(k[0].split('__')[-1] for k in holes))}")

    # longueur des prompts : trous vs reste
    def plen(key):
        pid, lang = key[0], key[1]
        base, variant = pid.split("__")[0], pid.split("__")[-1]
        row = ds.get(base)
        return len(build_prompt(row, variant, lang)) if row else None

    hl = [x for x in (plen(k) for k in holes) if x]
    if hl:
        print(f"    longueur des prompts en trou (car.) : "
              f"min={min(hl)} médiane={int(statistics.median(hl))} max={max(hl)}")

    if args.list_only:
        print("\n=== liste des trous ===")
        for k in sorted(holes):
            print(f"  {k[0]:22s} {k[1]}  ({plen(k)} car., {holes[k]} tentative(s))")
        return

    model = args.model or next(iter(holes))[2]
    print(f"\n[i] rejeu sur {min(args.limit, len(holes))} trou(s) | modèle : {model}")
    if args.num_ctx:
        print(f"[i] num_ctx forcé à {args.num_ctx}")

    options = {"temperature": 0.0}
    if args.num_ctx:
        options["num_ctx"] = args.num_ctx
    if args.num_predict:
        options["num_predict"] = args.num_predict

    reasons = Counter()
    refilled = 0
    for k in sorted(holes)[:args.limit]:
        pid, lang = k[0], k[1]
        base, variant = pid.split("__")[0], pid.split("__")[-1]
        row = ds.get(base)
        if not row:
            print(f"  {pid} {lang} : introuvable dans le dataset")
            continue
        prompt = build_prompt(row, variant, lang)
        try:
            r = requests.post(args.ollama_url, timeout=args.timeout, json={
                "model": model, "prompt": prompt, "stream": False, "options": options})
            r.raise_for_status()
            d = r.json()
        except Exception as exc:
            print(f"  {pid} {lang} : [ERROR] {exc}")
            reasons["http_error"] += 1
            continue

        resp = d.get("response", "")
        reason = d.get("done_reason", "?")
        pe, ev = d.get("prompt_eval_count"), d.get("eval_count")
        reasons[reason] += 1
        if resp.strip():
            refilled += 1
        flag = "REMPLI" if resp.strip() else "VIDE"
        print(f"  {pid:22s} {lang} | {len(prompt):6d} car. | done_reason={reason:7s} "
              f"| prompt_tok={pe} gen_tok={ev} | {flag}")
        if resp.strip():
            print(f"      -> {resp[:140].replace(chr(10), ' ')}")

    print(f"\n=== bilan ===")
    print(f"done_reason : {dict(reasons)}")
    print(f"rempli au rejeu : {refilled}/{min(args.limit, len(holes))}")
    if refilled == 0:
        print("Lecture : vide reproductible. Si prompt_tok plafonne à une valeur ronde "
              "(2048/4096/8192), c'est une TRONCATURE de contexte -> relance avec "
              "--num-ctx plus grand. Sinon c'est le modèle qui choisit de ne rien produire, "
              "et c'est un résultat à documenter (non-réponse, pas refus lexical).")
    else:
        print("Lecture : le vide n'était PAS déterministe dans ces conditions. "
              "Compare les réglages (num_ctx) avec ceux du run d'origine.")


if __name__ == "__main__":
    main()
