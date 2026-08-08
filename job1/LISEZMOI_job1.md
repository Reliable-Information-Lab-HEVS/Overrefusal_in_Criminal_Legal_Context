# Job 1 — Stabilité et décomposition de variance (v2, prompts corrigés)

Répond à Wuhrmann et al. (arXiv:2606.23375) : *27 % de la variance du refus provient du seul
échantillonnage*. Tes résultats reposent sur un tirage unique par cellule.

## Correction par rapport à la v1

La v1 rejouait la colonne `prompt` de `tf_para_llama31.csv` — c'est une colonne **d'aperçu
tronquée à 200 caractères** (100 % des lignes, écart-type nul), pas le prompt complet. Le
modèle ne recevait donc que la consigne et les trois premiers caractères du paragraphe, et
pour task02 le préfixe saturait à lui seul les 200 caractères : 4 prompts distincts sur 240.

Les prompts sont maintenant reconstruits depuis `data/bger_para_200.csv` selon la règle de
`INPUT_FORMAT.md` — `task<NN>_<lang>` + `"\n\n"` + `text_<lang>`.

**Vérification** : les 13 216 prompts du run principal ont été reconstruits et tronqués à
200 caractères ; **13 216 / 13 216 sont identiques à l'aperçu enregistré** (100,00 %). La
reconstruction est donc exacte, pas approchée.

Contrôles après correction : 240 prompts distincts par condition (attendu 240), longueur
moyenne 865 caractères (min 288, max 2 437).

## Le sous-échantillon (inchangé)

60 paragraphes BGer, seed 42, stratifiés par **régime de refus au run principal** de
llama3.1:8b (sur les 8 cellules = 4 langues × 2 conditions de chaque paragraphe) :

| strate | définition | population | tirés | poids |
|---|---|---:|---:|---:|
| S0_jamais | 0 refus / 8 | 452 | 20 | 22,60 |
| S1_bascule | 1–7 refus / 8 | 1 071 | 20 | 53,55 |
| S2_toujours | 8 refus / 8 | 129 | 20 | 6,45 |

Les 4 catégories sont représentées dans chaque strate. → **480 cellules**, dont 44,2 %
refusées au run principal. Conditionner sur l'issue est licite : on estime une *stabilité*,
pas un taux. Les poids d'inclusion permettent de remonter à la population.

## Ce qui est lancé

Générations nouvelles : la contrainte « ne pas repasser les réponses collectées dans un
LLM » est respectée.

| bras | température | k | seeds | appels | ce qu'il mesure |
|---|---|---:|---|---:|---|
| A | 0 | 3 | distincts | 1 440 | ton pipeline est-il déterministe ? |
| B | 0.7 | 5 | distincts | 2 400 | composante d'échantillonnage |

Total **3 840 appels**. Seeds distincts aussi dans le bras A : test fort de la déterminité à T=0.

Le script ne fait **aucune détection de refus** — il stocke la réponse brute. Tu appliques
ensuite ton détecteur mots-clés du run principal, pour garder un instrument identique.

## Avant de relancer

**Supprime les `job1_s*.csv` de la v1.** La reprise saute les clés déjà écrites : sans ça,
les 960 lignes tronquées seraient conservées sans que rien ne le signale.

## Procédure

**1. Smoke test.**

```bash
python run_job1.py --smoke
```

Ouvre `job1_smoke.csv` : les réponses doivent porter sur le contenu du paragraphe. Si tu lis
encore « je ne peux pas voir de document », arrête tout et dis-le moi.

**2. Débit.** Mesuré en v1 : ~3 600 appels/h — mais sur des prompts de 200 caractères avec
des réponses courtes. Avec les vrais prompts (865 c. en moyenne) et des réponses complètes,
compte plutôt 800–1 500 appels/h. Soit **2,5 à 5 h sur un seul processus, ~1 h sur 4 shards**.
Le script affiche le débit réel et l'ETA toutes les 25 réponses : lis-les avant de partir.

**3. Lancer.** Le sharding se fait maintenant **par paragraphe** — chaque shard couvre les
4 langues et les 2 conditions de 15 paragraphes, donc reste interprétable seul (en v1, le
shard 1 ne contenait que de l'allemand).

```bash
tmux new -s job1a
python run_job1.py --shard 1/4 --out job1_s1.csv --host http://localhost:11434 2>&1 | tee log_s1.txt
# Ctrl-b d, puis 2/4, 3/4, 4/4 sur les autres ports/instances Ollama
```

Rappel : 4 shards sur la même instance Ollama sans `OLLAMA_NUM_PARALLEL` font la queue.

**4. Reprise après coupure.** Relance la même commande : clés déjà écrites sautées, lignes
en erreur retentées.

## Le lendemain

```bash
# 1. applique ton detecteur mots-cles -> colonne is_refused
# 2.
python analyse_job1.py job1_s*.csv
```

Sorties : cellules unanimes par bras et par strate, décomposition between/within, part
stochastique à comparer à leurs 27 %, et le rapport `effet du préfixe / écart-type
stochastique` — c'est ce chiffre qui va dans le rapport.

## Fichiers

- `job1_prompts.csv` — 480 cellules, prompts complets vérifiés
- `job1_selection.csv` — les 60 paragraphes, strates et poids (trace méthodologique)
- `run_job1.py` — runner sans dépendance externe (stdlib + Ollama HTTP)
- `build_prompts.py` — reconstruction des prompts **et** sa vérification contre l'aperçu
- `build_sample.py` — le tirage stratifié, rejouable à l'identique (seed 42)
- `analyse_job1.py` — reproductibilité + décomposition de variance
