"""Reconstruit les prompts COMPLETS (task + "\n\n" + text, cf. INPUT_FORMAT.md)
et VERIFIE la reconstruction contre la colonne d'apercu du run principal."""
import pandas as pd

PARA = '/mnt/user-data/uploads/data/bger_para_200.csv'
RUN  = '/mnt/user-data/uploads/Resulats_FINAL/bger/tf_para_llama31.csv'
LANGS = ['fr', 'de', 'it', 'en']

src = pd.read_csv(PARA)
long = []
for _, r in src.iterrows():
    for lg in LANGS:
        for tv in ['task01', 'task02']:
            long.append({'para_id': r.prompt_id, 'lang': lg, 'task_variant': tv,
                         'category': r.category,
                         'prompt': f'{r[f"{tv}_{lg}"]}\n\n{r[f"text_{lg}"]}'})
long = pd.DataFrame(long)
long['prompt_id'] = long.para_id + '__' + long.task_variant

# --- VERIFICATION : la troncature a 200 c. doit redonner exactement l'apercu du run principal
run = pd.read_csv(RUN)[['prompt_id', 'lang', 'prompt']].rename(columns={'prompt': 'apercu'})
chk = run.merge(long[['prompt_id', 'lang', 'prompt']], on=['prompt_id', 'lang'], how='left')
chk['recons'] = chk.prompt.str[:200]
ok = (chk.recons == chk.apercu)
print(f'verification : {ok.sum()}/{len(chk)} prompts reconstruits identiques a l apercu du run '
      f'principal sur les 200 premiers caracteres ({ok.mean():.2%})')
if not ok.all():
    print(chk[~ok].head(3)[['prompt_id', 'lang']].to_string())
    raise SystemExit('!! reconstruction non conforme, on ne lance rien')

# --- on rejoue la selection deja tiree (seed 42), on ne retire pas
sel = pd.read_csv('job1_selection.csv')
cells = long[long.para_id.isin(sel.para_id)].merge(
    sel[['para_id', 'strate', 'poids_inclusion']], on='para_id')
ref = pd.read_csv(RUN)[['prompt_id', 'lang', 'is_refused']].rename(
    columns={'is_refused': 'refus_run_principal'})
cells = cells.merge(ref, on=['prompt_id', 'lang'])
cells = cells[['prompt_id', 'para_id', 'category', 'task_variant', 'lang', 'prompt',
               'refus_run_principal', 'strate', 'poids_inclusion']]
cells = cells.sort_values(['para_id', 'task_variant', 'lang']).reset_index(drop=True)
cells.to_csv('job1_prompts.csv', index=False)

print(f'\njob1_prompts.csv : {len(cells)} cellules, {cells.para_id.nunique()} paragraphes')
print('prompts distincts :', cells.groupby("task_variant").prompt.nunique().to_dict(), '/ attendu 240 chacun')
print('longueur des prompts :')
print(cells.groupby('task_variant').prompt.apply(lambda s: s.str.len()).describe().round(0).to_string())
print('\nrefus au run principal :', int(cells.refus_run_principal.sum()),
      f'({cells.refus_run_principal.mean():.1%})')
