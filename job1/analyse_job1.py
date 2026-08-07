#!/usr/bin/env python3
"""
Analyse du Job 1 — reproductibilite (bras A) et decomposition de variance (bras B).

Prealable : appliquer TON detecteur mots-cles du run principal sur la colonne
`response_full` et ajouter une colonne booleenne `is_refused`. Instrument identique
au run principal = comparaison valide. Puis :

    python analyse_job1.py job1_A*.csv job1_B*.csv
"""
import sys, glob, pandas as pd, numpy as np

CELL = ["prompt_id", "lang"]           # une cellule = (paragraphe x condition x langue)

def charger(motifs):
    fs = [f for m in motifs for f in glob.glob(m)]
    df = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True)
    df = df[df.is_error != True]
    df = df.drop_duplicates(subset="cle", keep="last")          # reprises : derniere ecriture
    if "is_refused" not in df.columns:
        sys.exit("!! colonne 'is_refused' absente : applique d'abord ton detecteur mots-cles.")
    df["is_refused"] = df.is_refused.astype(bool)
    return df

def repro(sub):
    """Bras A : part des cellules dont les k repetitions sont unanimes."""
    g = sub.groupby(CELL).is_refused.agg(["mean", "size"])
    return (g["mean"].isin([0.0, 1.0])).mean(), len(g)

def decomposition(sub):
    """Var_between (contenu/langue/condition) vs Var_within (echantillonnage)."""
    g = sub.groupby(CELL).is_refused.agg(p="mean", k="size")
    g = g[g.k >= 2]
    within = (g.p * (1 - g.p) * g.k / (g.k - 1)).mean()          # estimateur sans biais
    between = g.p.var(ddof=1) - within / g.k.mean()
    between = max(between, 0.0)
    total = between + within
    return {"cellules": len(g), "k_moyen": round(g.k.mean(), 2),
            "var_between": between, "var_within": within,
            "part_stochastique": within / total if total else np.nan,
            "icc": between / total if total else np.nan,
            "sd_stochastique_pts": 100 * np.sqrt(within)}

def main():
    df = charger(sys.argv[1:] or ["job1_*.csv"])
    df["condition"] = df.task_variant.map({"task01": "none", "task02": "prefixe"})
    print(f"{len(df)} reponses valides | {df.groupby(CELL).ngroups} cellules\n")

    for bras, sub in df.groupby("bras"):
        cfg = "T=0" if bras == "A" else "T=0.7"
        print(f"=== bras {bras} ({cfg}) ===")
        r, n = repro(sub)
        print(f"cellules unanimes sur leurs repetitions : {r:.1%}  (n={n})")
        for s, ss in sub.groupby("strate"):
            rs, ns = repro(ss)
            print(f"   {s:<12} {rs:6.1%}  (n={ns})")
        if bras == "B":
            d = decomposition(sub)
            print(f"\n   decomposition de variance ({d['cellules']} cellules, k={d['k_moyen']})")
            print(f"   part imputable a l'echantillonnage : {d['part_stochastique']:.1%}"
                  f"   [Wuhrmann et al. : 27 %]")
            print(f"   ICC (part stable)                 : {d['icc']:.1%}")
            print(f"   ecart-type stochastique           : {d['sd_stochastique_pts']:.1f} pts")
        print()

    # --- l'argument de fond : effet du prefixe vs bruit, sur les memes cellules
    b = df[df.bras == "B"]
    if len(b):
        cel = b.groupby(CELL + ["condition", "strate", "poids_inclusion"]).is_refused.mean().reset_index()
        w = cel.groupby("condition").apply(
            lambda x: np.average(x.is_refused, weights=x.poids_inclusion))
        effet = 100 * (w.get("prefixe", np.nan) - w.get("none", np.nan))
        sd = decomposition(b)["sd_stochastique_pts"]
        print("=== effet du prefixe vs composante stochastique (ponderé) ===")
        print(f"none {100*w.get('none', np.nan):.1f} %  ->  prefixe {100*w.get('prefixe', np.nan):.1f} %"
              f"   delta {effet:+.1f} pts")
        print(f"rapport delta / ecart-type stochastique : {abs(effet)/sd:.1f}x")
        print("\nNB : les taux ci-dessus sont ceux du sous-echantillon stratifie (ponderes).")
        print("     Les taux de reference du memoire restent ceux du run complet.")

if __name__ == "__main__":
    main()
