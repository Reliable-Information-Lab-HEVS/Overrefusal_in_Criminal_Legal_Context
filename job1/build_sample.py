import pandas as pd, numpy as np, json

SEED = 42
SRC  = '/mnt/user-data/uploads/Resulats_FINAL/bger/tf_para_llama31.csv'

df = pd.read_csv(SRC)
df['para_id'] = df['prompt_id'].str.replace(r'__task0[12]$', '', regex=True)

# --- regime de chaque paragraphe : nb de refus sur ses 8 cellules (4 langues x 2 conditions)
reg = df.groupby(['para_id', 'category']).is_refused.sum().reset_index(name='n_refus')
def strate(n):
    if n == 0: return 'S0_jamais'
    if n == 8: return 'S2_toujours'
    return 'S1_bascule'
reg['strate'] = reg.n_refus.map(strate)

# --- allocation des 20 slots par strate, proportionnelle aux categories, plancher de 2
rng = np.random.default_rng(SEED)
picked = []
for s, sub in reg.groupby('strate'):
    comp = sub.category.value_counts()
    n_target = 20
    alloc = {}
    # plancher de 2 pour toute categorie presente (ou son effectif si < 2)
    for c, n in comp.items():
        alloc[c] = min(2, n)
    reste = n_target - sum(alloc.values())
    # largest remainder sur le reste, plafonne par l'effectif disponible
    parts = (comp / comp.sum() * reste)
    order = sorted(parts.index, key=lambda c: (-parts[c], c))
    for c in order:
        add = int(np.floor(parts[c]))
        add = min(add, comp[c] - alloc[c])
        alloc[c] += add
    while sum(alloc.values()) < n_target:
        for c in order:
            if alloc[c] < comp[c]:
                alloc[c] += 1
                if sum(alloc.values()) == n_target: break
    for c, k in alloc.items():
        cand = sub[sub.category == c].para_id.sort_values().to_numpy()
        take = rng.choice(cand, size=k, replace=False)
        for p in take:
            picked.append({'para_id': p, 'category': c, 'strate': s,
                           'n_refus_run_principal': int(sub.loc[sub.para_id == p, 'n_refus'].iloc[0]),
                           'N_strate': len(sub), 'n_tires': n_target})
sel = pd.DataFrame(picked)
sel['poids_inclusion'] = (sel.N_strate / sel.n_tires).round(4)
sel = sel.sort_values(['strate', 'category', 'para_id']).reset_index(drop=True)

# --- rejeu exact des prompts : on reprend la chaine envoyee lors du run principal
cols = ['prompt_id', 'para_id', 'category', 'task_variant', 'lang', 'prompt', 'is_refused']
cells = df[df.para_id.isin(sel.para_id)][cols].rename(columns={'is_refused': 'refus_run_principal'})
cells = cells.merge(sel[['para_id', 'strate', 'poids_inclusion']], on='para_id')
cells = cells.sort_values(['para_id', 'task_variant', 'lang']).reset_index(drop=True)

sel.to_csv('job1_selection.csv', index=False)
cells.to_csv('job1_prompts.csv', index=False)

print('=== strates ===')
print(sel.groupby('strate').agg(paragraphes=('para_id','size'), N_population=('N_strate','first'),
                                poids=('poids_inclusion','first')).to_string())
print()
print('=== categories par strate ===')
print(pd.crosstab(sel.strate, sel.category).to_string())
print()
print('cellules a rejouer :', len(cells), '(', cells.para_id.nunique(), 'paragraphes x',
      cells.lang.nunique(), 'langues x', cells.task_variant.nunique(), 'conditions )')
print('dont refusees au run principal :', int(cells.refus_run_principal.sum()),
      f'({cells.refus_run_principal.mean():.1%})')
print()
print('=== appels ===')
print('bras A  T=0    k=3 :', len(cells)*3)
print('bras B  T=0.7  k=5 :', len(cells)*5)
print('total              :', len(cells)*8)
