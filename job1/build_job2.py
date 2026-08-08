"""Job 2 — concordance langue d'instruction x langue du document.

Wuhrmann et al. : rediger l'instruction dans la langue du texte source plutot que dans la
langue cible augmente le refus (OR 1,6 Llama / 2,6 GPT-OSS). Toutes les cellules du run
principal sont concordantes (instruction et document dans la meme langue), donc l'effet
"anglais" de H3 peut venir du document OU de la consigne. Ce job tranche.

Manipulation : document en fr/de/it, instruction (prefixe compris) en ANGLAIS.
Comparaison : les cellules concordantes du bras A de job 1, deja mesurees.
"""
import pandas as pd

PARA = '/mnt/user-data/uploads/data/bger_para_200.csv'
sel  = pd.read_csv('job1_selection.csv')
src  = pd.read_csv(PARA)
src  = src[src.prompt_id.isin(sel.para_id)]

rows = []
for _, r in src.iterrows():
    for doc in ['fr', 'de', 'it']:                     # en : concordant par construction
        for tv in ['task01', 'task02']:
            rows.append({
                'prompt_id'  : f'{r.prompt_id}__{tv}__instrEN',
                'para_id'    : r.prompt_id,
                'category'   : r.category,
                'task_variant': tv,
                'lang'       : doc,                    # langue du DOCUMENT
                'lang_instr' : 'en',                   # langue de l'INSTRUCTION
                'prompt'     : f'{r[f"{tv}_en"]}\n\n{r[f"text_{doc}"]}',
            })
d = pd.DataFrame(rows).merge(sel[['para_id','strate','poids_inclusion']], on='para_id')
d = d.sort_values(['para_id','task_variant','lang']).reset_index(drop=True)
d.to_csv('job2_prompts.csv', index=False)

print(f'{len(d)} cellules | {d.para_id.nunique()} paragraphes x {d.lang.nunique()} langues '
      f'x {d.task_variant.nunique()} conditions')
print('prompts distincts :', d.groupby("task_variant").prompt.nunique().to_dict(), '/ attendu 180')
print('longueur des prompts :', d.prompt.str.len().describe()[['min','50%','max']].round(0).to_dict())
print('\nappels : T=0 k=1 -> 360 | T=0.7 k=3 -> 1080 | total 1440')
print('\n--- exemple (document allemand, instruction anglaise, task02) ---')
e = d[(d.lang=='de') & (d.task_variant=='task02')].iloc[0]
print(e.prompt[:420].replace('\n','\n  '))
