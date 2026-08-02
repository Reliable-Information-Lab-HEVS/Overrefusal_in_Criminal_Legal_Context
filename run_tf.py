#!/usr/bin/env python3
"""
run_tf.py — Lancement ROBUSTE et REPRENABLE de l'évaluation sur-refus.

Réutilise ton pipeline existant (package over_refusal) : mêmes prompts
(get_all_prompts), mêmes clients (models.yaml -> Ollama / OpenAI-compatible),
même détecteur de refus, mêmes colonnes de sortie que run.py.

La SEULE différence avec run.py : chaque réponse est écrite sur le disque
IMMÉDIATEMENT, et un relancement REPREND où ça s'est arrêté (il saute les
(prompt_id, langue, modèle) déjà présents dans le fichier de sortie). C'est ce
qui rend un run de nuit sur le 70B — et la vague paragraphes du week-end —
sûrs : une coupure ne perd rien.

Un modèle par appel = un cluster par appel. Le modèle et son base_url de cluster
viennent de models.yaml ; --model sélectionne l'entrée par son "name" en gardant
son client (donc son base_url).

Exemples (les deux clusters, chacun son fichier, chacun reprenable) :
  python run_tf.py --prompts-file data/bger_dataset.csv --model llama3.1:8b \
      --languages fr de it en --output results/tf_full_llama31_8b.csv

  python run_tf.py --prompts-file data/bger_dataset.csv --model llama3.3:70b \
      --languages fr de it en --output results/tf_full_llama33_70b.csv

Relancer après une coupure : la MÊME commande. Ça reprend.
"""
import argparse
import csv
import sys
import time
from pathlib import Path

from over_refusal.clients import resolve_models
from over_refusal.prompts import get_all_prompts, TASK_MODES
from over_refusal.detector import RefusalDetector
from over_refusal.config import SUPPORTED_LANGUAGES, DEFAULT_RESULTS_DIR

# Mêmes colonnes que storage.py / evaluation.py (compatibles avec ton analyse).
FIELDS = ["prompt_id", "category", "task_variant", "lang", "model", "backend",
          "prompt", "response_preview", "response_full", "is_refused", "is_error"]
PROMPT_PREVIEW_CHARS = 200
RESPONSE_PREVIEW_CHARS = 500


def load_done(path: Path, retry_empty: int = 2):
    """Clés (prompt_id, lang, model) considérées comme traitées.

    Les lignes en erreur ([ERROR] : timeout, modèle absent, …) ne comptent PAS
    comme faites : elles sont RETENTÉES à la reprise (leçon de la séance 26,
    faux résultats dus aux read timeouts). Le CSV garde alors l'ancienne ligne
    erreur + la nouvelle tentative ; à l'analyse, écarter les is_error=True
    (la dernière tentative par clé fait foi).

    Les RÉPONSES VIDES (HTTP 200 mais champ "response" vide : le modèle n'a rien
    produit) sont un cas distinct. Ce n'est pas une erreur réseau, et à
    temperature 0 c'est souvent DÉTERMINISTE : retenter à l'infini ne remplit
    jamais le trou et le run refait les mêmes N appels à chaque lancement. On
    retente donc au plus `retry_empty` fois, puis la clé est déclarée épuisée
    (vide reproductible) et le run peut se terminer.
    """
    csv.field_size_limit(10 ** 8)
    ok = set()
    empty_tries = {}
    errors = 0
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                key = (r["prompt_id"], r["lang"], r["model"])
                if (r.get("is_error") or "").strip() == "True":
                    errors += 1
                    continue
                if not (r.get("response_full") or "").strip():
                    empty_tries[key] = empty_tries.get(key, 0) + 1
                    continue
                ok.add(key)
    exhausted = {k for k, n in empty_tries.items() if k not in ok and n >= retry_empty}
    pending = {k for k in empty_tries if k not in ok and k not in exhausted}
    if errors:
        print(f"[i] {errors} ligne(s) en erreur dans {path.name} -> seront retentées.")
    if exhausted:
        print(f"[i] {len(exhausted)} clé(s) à réponse VIDE reproductible "
              f"(>= {retry_empty} tentatives) -> abandonnées, plus retentées.")
        print("    Ce n'est pas une panne : le modèle renvoie du vide sur ces prompts.")
        print("    Diagnostic : python probe_empty.py --results <csv> --prompts-file <dataset>")
    if pending:
        print(f"[i] {len(pending)} clé(s) à réponse vide -> une nouvelle tentative.")
    return ok | exhausted


def main():
    ap = argparse.ArgumentParser(description="Run reprenable de l'éval sur-refus (1..N modèles).")
    ap.add_argument("--prompts-file", required=True)
    ap.add_argument("--model", nargs="*", default=None,
                    help="un ou plusieurs 'name' de models.yaml (ex. llama3.1:8b gemma3:4b). "
                         "Omis = TOUS les modèles de models.yaml.")
    ap.add_argument("--models-file", default=None, help="chemin de models.yaml (défaut : racine du repo)")
    ap.add_argument("--languages", nargs="+", default=SUPPORTED_LANGUAGES,
                    choices=SUPPORTED_LANGUAGES, help="défaut : fr de it en")
    ap.add_argument("--output", required=True, help="CSV de sortie (repris s'il existe déjà)")
    ap.add_argument("--limit", type=int, default=None, help="limite le nb d'arrêts (après filtres)")
    ap.add_argument("--categories", nargs="+", default=None)
    ap.add_argument("--prompt-ids", nargs="+", default=None)
    ap.add_argument("--task-mode", choices=list(TASK_MODES), default="task01")
    ap.add_argument("--sleep", type=float, default=0.0, help="pause entre appels (s)")
    ap.add_argument("--quiet", action="store_true",
                    help="n'affiche pas l'aperçu de la réponse (statut seul)")
    ap.add_argument("--retry-empty", type=int, default=2,
                    help="nb max de tentatives sur une réponse VIDE avant abandon "
                         "(défaut 2 ; 0 = ne jamais retenter une réponse vide)")
    args = ap.parse_args()

    # 1) modèles depuis models.yaml, en gardant leur client (donc leur base_url).
    specs = resolve_models(models_file=args.models_file)
    by_name = {s.name: s for s in specs}
    if args.model:
        missing = [m for m in args.model if m not in by_name]
        if missing:
            sys.exit(f"[STOP] modèle(s) introuvable(s) dans models.yaml : {missing}. "
                     f"Disponibles : {list(by_name)}")
        chosen = [by_name[m] for m in args.model]
    else:
        chosen = specs  # tous
    if not chosen:
        sys.exit("[STOP] aucun modèle sélectionné (models.yaml vide ?).")

    # 2) prompts, construits EXACTEMENT comme run.py (task01 + '\\n\\n' + texte).
    prompts = get_all_prompts(csv_path=args.prompts_file, categories=args.categories,
                              prompt_ids=args.prompt_ids, limit=args.limit,
                              task_mode=args.task_mode)
    if not prompts:
        sys.exit("[STOP] aucun prompt (vérifie le fichier / les filtres).")

    detector = RefusalDetector()

    out = Path(args.output)
    if not out.is_absolute() and out.parent == Path("."):
        out = Path(DEFAULT_RESULTS_DIR) / out.name
    out.parent.mkdir(parents=True, exist_ok=True)

    done = load_done(out, retry_empty=args.retry_empty)
    new_file = not out.exists()
    total = len(prompts) * len(args.languages) * len(chosen)
    todo = total - len(done)

    print(f"[i] modèles : {[s.name for s in chosen]}")
    print(f"[i] {len(prompts)} arrêts x {len(args.languages)} langues x {len(chosen)} modèles "
          f"= {total} appels | déjà faits : {len(done)} | à faire : {todo}")
    print(f"[i] sortie : {out}")
    if todo <= 0:
        print("[✓] rien à faire, tout est déjà là.")
        return

    n = 0
    with open(out, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
            fh.flush()
        # un modèle après l'autre (fini un modèle avant de passer au suivant)
        for spec in chosen:
            for pid, pdata in prompts.items():
                for lang in args.languages:
                    if (pid, lang, spec.name) in done:
                        continue
                    # même repli que run.py : anglais si la langue manque
                    prompt_text = pdata.get(lang) or pdata.get("en", "")
                    if not prompt_text:
                        print(f"[skip] {pid} : pas de texte en '{lang}'")
                        continue

                    n += 1
                    print(f"[{n}/{todo}] {pid} | {lang} | {spec.name} ...", end=" ", flush=True)

                    resp = spec.client.query(prompt_text, spec.name)
                    is_error = resp.startswith("[ERROR]")
                    refused = detector.is_refusal(resp, lang)
                    preview = resp if is_error else resp[:RESPONSE_PREVIEW_CHARS].replace("\n", " ")

                    w.writerow({
                        "prompt_id": pid,
                        "category": pdata["category"],
                        "task_variant": pdata.get("task_variant", "task01"),
                        "lang": lang,
                        "model": spec.name,
                        "backend": spec.backend,
                        "prompt": prompt_text[:PROMPT_PREVIEW_CHARS],
                        "response_preview": preview,
                        "response_full": resp,
                        "is_refused": refused,
                        "is_error": is_error,
                    })
                    fh.flush()  # <-- chaque réponse est sur le disque tout de suite

                    if is_error:
                        status = "ERROR"
                    elif not resp.strip():
                        status = "EMPTY"      # 200 OK mais le modèle n'a rien produit
                    elif refused:
                        status = "REFUSED"
                    else:
                        status = "OK"
                    print(status)
                    if not args.quiet:
                        print(f"    -> {preview[:300]}")
                    if args.sleep:
                        time.sleep(args.sleep)

    print(f"\n[✓] terminé. Résultats : {out}")
    print("    (relancer la même commande reprend automatiquement s'il reste des appels)")


if __name__ == "__main__":
    main()
