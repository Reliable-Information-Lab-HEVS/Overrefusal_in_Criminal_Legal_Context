# Job 1 — Stabilité et décomposition de variance

Répond à l'objection de Wuhrmann et al. (arXiv:2606.23375) : *27 % de la variance du refus
provient du seul échantillonnage*. Tes résultats reposent sur un tirage unique par cellule.

## Le sous-échantillon

60 paragraphes BGer, seed 42, stratifiés par **régime de refus au run principal** (llama3.1:8b,
sur les 8 cellules = 4 langues × 2 conditions de chaque paragraphe) :

| strate | définition | population | tirés | poids |
|---|---|---:|---:|---:|
| S0_jamais | 0 refus / 8 | 452 | 20 | 22,60 |
| S1_bascule | 1–7 refus / 8 | 1 071 | 20 | 53,55 |
| S2_toujours | 8 refus / 8 | 129 | 20 | 6,45 |

Les 4 catégories sont représentées dans chaque strate. → **480 cellules**, dont 44,2 % refusées
au run principal. Conditionner sur l'issue est licite : on estime une *stabilité*, pas un taux.
Les poids d'inclusion permettent de remonter à la population si besoin.

Affinement par rapport au plan initial (30 refusés / 30 non) : la strate S1 est celle où la
variance vit réellement, elle méritait d'être isolée.

## Ce qui est lancé

Rejeu **exact** des chaînes de prompt du run principal — aucune reconstruction, aucun risque
de dérive. Ce sont des générations nouvelles : la contrainte « ne pas repasser les réponses
collectées dans un LLM » est respectée.

| bras | température | k | seeds | appels | ce qu'il mesure |
|---|---|---:|---|---:|---|
| A | 0 | 3 | distincts | 1 440 | ton pipeline est-il déterministe ? |
| B | 0.7 | 5 | distincts | 2 400 | composante d'échantillonnage |

Total **3 840 appels**. Seeds distincts aussi dans le bras A : c'est le test fort de la
déterminité à T=0.

Le script ne fait **aucune détection de refus** — il stocke la réponse brute. Tu appliques
ensuite ton détecteur mots-clés du run principal, pour garder un instrument identique.

## Procédure

**1. Smoke test (2 min, à faire avant tout).**

```bash
python run_job1.py --smoke
```

Vérifie que ça écrit `job1_smoke.csv` avec 8 réponses non vides. Note le débit affiché
(`appels/h`) : c'est lui qui décide du nombre de shards.

**2. Choisir le découpage.** Avec un débit mesuré de D appels/h par GPU et N shards,
la nuit dure `3840 / (N × D)` heures. À ~165 appels/h : 2 shards → 11,6 h ; 3 shards → 7,8 h ;
4 shards → 5,8 h. Prends la marge, tu veux que ce soit fini au réveil.

**3. Lancer (exemple à 4 shards, un par GPU/instance Ollama).**

```bash
tmux new -s job1a
python run_job1.py --shard 1/4 --out job1_s1.csv --host http://localhost:11434 2>&1 | tee log_s1.txt
# Ctrl-b d, puis idem pour les shards 2/4, 3/4, 4/4 sur les autres ports/machines
```

Les shards sont disjoints et chacun couvre les deux bras. L'ordre d'exécution est
répétition par répétition : si tu coupes en cours, tu as quand même des cellules complètes
sur les premières répétitions.

**4. Avant d'aller dormir.** Regarde une ligne de progression :
`[job1] 25/960 | 168 appels/h | erreurs 0 | ETA 5.6 h`. Si le nombre d'erreurs monte
(timeouts), augmente `--timeout` et relance — la reprise est automatique.

**5. Reprise après coupure.** Relance exactement la même commande : les clés déjà écrites
sont sautées, les lignes en erreur sont retentées.

## Le lendemain

```bash
# 1. applique ton detecteur mots-cles -> colonne is_refused
# 2.
python analyse_job1.py job1_s*.csv
```

Sorties : taux de cellules unanimes par bras et par strate, décomposition
between/within, part stochastique à comparer à leurs 27 %, et le rapport
`effet du préfixe / écart-type stochastique` — c'est ce chiffre qui va dans le rapport.

## Fichiers

- `job1_prompts.csv` — 480 cellules avec la chaîne de prompt exacte et l'issue du run principal
- `job1_selection.csv` — les 60 paragraphes, strates et poids d'inclusion (trace méthodologique)
- `run_job1.py` — le runner (écriture incrémentale, reprise par clé, sharding, timeout 300)
- `analyse_job1.py` — reproductibilité + décomposition de variance
- `build_sample.py` — le tirage, rejouable à l'identique (seed 42)
