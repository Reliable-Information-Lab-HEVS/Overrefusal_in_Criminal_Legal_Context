#!/usr/bin/env python3
"""
Ré-étiquette job1_all.csv avec le VRAI détecteur de refus du repo,
puis compare à la reconstruction (colonne is_refused de job1_all_labelled.csv).

À lancer depuis la racine du repo :
    python relabel_repo.py job1/job1_all.csv job1/job1_all_labelled.csv
"""
import sys, csv, inspect, importlib, pkgutil

CSV_IN  = sys.argv[1] if len(sys.argv) > 1 else 'job1_all.csv'
CSV_CMP = sys.argv[2] if len(sys.argv) > 2 else None
OUT     = 'job1_all_repo.csv'

# ---------- 1. trouver le detecteur ----------
def candidats():
    import over_refusal
    mods = [over_refusal]
    for m in pkgutil.iter_modules(over_refusal.__path__):
        try: mods.append(importlib.import_module(f'over_refusal.{m.name}'))
        except Exception: pass
    for mod in mods:
        for nom, obj in vars(mod).items():
            if not callable(obj) or nom.startswith('_'): continue
            if not any(k in nom.lower() for k in ('refus', 'refusal', 'detect')): continue
            try:
                if len(inspect.signature(obj).parameters) >= 1:
                    yield f'{mod.__name__}.{nom}', obj
            except (ValueError, TypeError):
                pass

trouves = list(candidats())
if not trouves:
    sys.exit("Aucun detecteur trouve dans over_refusal.\n"
             "Lance :  grep -rn 'def .*refus\\|REFUSAL\\|keyword' over_refusal/*.py\n"
             "puis remplace la fonction 'detect' ci-dessous par le bon import.")
print('candidats trouves :')
for nom, _ in trouves: print('  -', nom)

# on garde le premier qui accepte une chaine et renvoie un booleen
detect = None
for nom, fn in trouves:
    try:
        r = fn("I cannot provide legal advice. Is there anything else I can help you with?")
        r2 = fn("Here are the key facts: A. was born in 1979 in Portugal and holds a B permit.")
        if isinstance(r, (bool, int)) and bool(r) and not bool(r2):
            detect = fn; print(f'\n-> retenu : {nom}'); break
    except Exception:
        continue
if detect is None:
    sys.exit("Aucun candidat ne se comporte comme un detecteur (refus=True, reponse=False).\n"
             "Choisis-le a la main dans la liste ci-dessus.")

# ---------- 2. appliquer ----------
lignes = list(csv.DictReader(open(CSV_IN, encoding='utf-8')))
for r in lignes:
    r['is_refused'] = bool(detect(r['response_full']))
champs = [c for c in lignes[0] if c != 'is_refused'] + ['is_refused']
with open(OUT, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=champs, extrasaction='ignore')
    w.writeheader(); w.writerows(lignes)
n = sum(r['is_refused'] for r in lignes)
print(f'\n{OUT} ecrit | {len(lignes)} lignes | {n} refus ({n/len(lignes):.1%})')

# ---------- 3. comparer a la reconstruction ----------
if CSV_CMP:
    ref = {r['cle']: r['is_refused'] == 'True' for r in csv.DictReader(open(CSV_CMP, encoding='utf-8'))}
    dif = [r for r in lignes if r['cle'] in ref and r['is_refused'] != ref[r['cle']]]
    print(f'ecarts avec la reconstruction : {len(dif)} / {len(ref)} '
          f'({len(dif)/len(ref):.3%})')
    for r in dif[:5]:
        print(f"  [{r['lang']} {r['task_variant']}] repo={r['is_refused']} "
              f"recons={ref[r['cle']]} :: {r['response_full'][:110]!r}")
