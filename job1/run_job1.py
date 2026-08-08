#!/usr/bin/env python3
"""
Job 1 — Stabilite et decomposition de variance (llama3.1:8b, BGer paragraphes).

Rejeu EXACT des prompts du run principal sur un sous-echantillon stratifie de
60 paragraphes x 4 langues x 2 conditions = 480 cellules.

  bras A : temperature 0,   k=3 repetitions, seeds distincts -> le pipeline est-il deterministe ?
  bras B : temperature 0.7, k=5 repetitions, seeds distincts -> composante d'echantillonnage
                                                                (comparable aux 27% de Wuhrmann et al.)

Aucune detection de refus ici : on stocke la reponse brute et on applique
ENSUITE le detecteur mots-cles du run principal, pour garder un instrument identique.

Usage
  python run_job1.py --smoke                          # 8 appels, verification en ~2 min
  python run_job1.py --arm A --shard 1/2 --out A1.csv
  python run_job1.py --arm A --shard 2/2 --out A2.csv --host http://localhost:11435
  python run_job1.py --arm B --shard 1/2 --out B1.csv
  python run_job1.py --arm B --shard 2/2 --out B2.csv --host http://localhost:11435

Relancer la meme commande apres une coupure : les cles deja ecrites sont
sautees, les lignes en erreur sont retentees.
"""
import argparse, csv, json, os, sys, time
import urllib.request, urllib.error

ARMS = {
    "A": {"temperature": 0.0, "k": 3},
    "B": {"temperature": 0.7, "k": 5},
}

def parser_arms(spec):
    """--arm-spec "C=0:1,D=0.7:3"  ->  redefinit les bras."""
    out = {}
    for bloc in spec.split(","):
        nom, reste = bloc.split("=")
        t, k = reste.split(":")
        out[nom.strip()] = {"temperature": float(t), "k": int(k)}
    return out
FIELDS = ["cle", "bras", "rep", "seed", "temperature", "prompt_id", "para_id", "category",
          "task_variant", "lang", "lang_instr", "strate", "poids_inclusion", "refus_run_principal",
          "response_full", "n_char", "duree_s", "is_error", "erreur"]


def charger_prompts(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def construire_travail(lignes, bras_demande, k_override=None):
    travail = []
    noms = list(ARMS)
    for bras in (noms if bras_demande in ("AB", "".join(noms)) else [bras_demande]):
        cfg = ARMS[bras]
        k = k_override or cfg["k"]
        for rep in range(1, k + 1):
            for r in lignes:
                cle = f'{r["prompt_id"]}|{r["lang"]}|{bras}|{rep}'
                travail.append({**r, "cle": cle, "bras": bras, "rep": rep,
                                "seed": 1000 * rep + 42,
                                "temperature": cfg["temperature"]})
    # ordre stable : toutes les cellules de rep 1, puis rep 2... (resultats exploitables si coupure)
    travail.sort(key=lambda t: (t["bras"], t["rep"], t["prompt_id"], t["lang"]))
    return travail


def appliquer_shard(travail, shard):
    """Shard PAR PARAGRAPHE : chaque shard couvre les 4 langues et les 2 conditions
    d'un sous-ensemble de paragraphes. Un shard reste donc interpretable seul."""
    if not shard:
        return travail
    i, n = (int(x) for x in shard.split("/"))
    paras = sorted({t["para_id"] for t in travail})
    mien = {p for j, p in enumerate(paras) if j % n == (i - 1)}
    return [t for t in travail if t["para_id"] in mien]


def deja_fait(path):
    """Cles deja ecrites ET valides. Les lignes en erreur seront retentees."""
    ok, err = set(), set()
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                (err if row.get("is_error") == "True" else ok).add(row["cle"])
    return ok, err - ok


def generer(host, model, prompt, temperature, seed, timeout):
    payload = json.dumps({
        "model": model, "prompt": prompt, "stream": False, "keep_alive": "30m",
        "options": {"temperature": temperature, "seed": seed},
    }).encode()
    req = urllib.request.Request(f"{host}/api/generate", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as rep:
        return json.loads(rep.read()).get("response", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", default="job1_prompts.csv")
    ap.add_argument("--out", default="job1_resultats.csv")
    ap.add_argument("--arm", default="AB")
    ap.add_argument("--arm-spec", default=None,
                    help='redefinit les bras, ex. "C=0:1,D=0.7:3"')
    ap.add_argument("--shard", default=None, help="ex. 1/2")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--smoke", action="store_true", help="8 appels de verification")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    global ARMS
    if a.arm_spec:
        ARMS = parser_arms(a.arm_spec)
        if a.arm == "AB":
            a.arm = "".join(ARMS)
    lignes = charger_prompts(a.prompts)
    if a.smoke:
        lignes, a.arm, a.out = lignes[:4], "A", "job1_smoke.csv"
        travail = construire_travail(lignes, "A", k_override=2)
    else:
        travail = appliquer_shard(construire_travail(lignes, a.arm), a.shard)

    ok, a_retenter = deja_fait(a.out)
    restant = [t for t in travail if t["cle"] not in ok]
    print(f"[job1] modele={a.model} hote={a.host} bras={a.arm} shard={a.shard or '1/1'}", flush=True)
    print(f"[job1] {len(travail)} appels prevus | {len(ok)} deja faits | "
          f"{len(a_retenter)} erreurs a retenter | {len(restant)} a lancer", flush=True)
    if not restant:
        print("[job1] rien a faire."); return

    nouveau = not os.path.exists(a.out)
    t0, n_err = time.time(), 0
    with open(a.out, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if nouveau:
            w.writeheader(); f.flush()
        for i, t in enumerate(restant, 1):
            d0 = time.time()
            try:
                rep = generer(a.host, a.model, t["prompt"], t["temperature"], t["seed"], a.timeout)
                t.update(response_full=rep, n_char=len(rep), is_error=False, erreur="")
            except Exception as e:
                n_err += 1
                t.update(response_full="", n_char=0, is_error=True, erreur=f"{type(e).__name__}: {e}"[:300])
            t["duree_s"] = round(time.time() - d0, 2)
            w.writerow(t); f.flush()
            if not a.quiet and (i % 25 == 0 or i == len(restant)):
                ecoule = time.time() - t0
                debit = i / ecoule * 3600
                eta = (len(restant) - i) / max(debit, 1e-9) * 3600
                print(f"[job1] {i}/{len(restant)} | {debit:.0f} appels/h | "
                      f"erreurs {n_err} | ETA {eta/3600:.1f} h", flush=True)
    print(f"[job1] termine en {(time.time()-t0)/3600:.2f} h, {n_err} erreur(s). "
          f"Relancer la meme commande pour retenter les erreurs.", flush=True)


if __name__ == "__main__":
    main()
