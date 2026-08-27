# Fill the task columns of bger_sample20_summary_judge.csv from bger_sample.csv.
# normal = extraction instruction; hard = supreme-court prefix + same instruction.
import csv
from pathlib import Path

TASK_FR = (
    "Examinez le document juridique suivant et, sans rien omettre, relevez les "
    "faits essentiels, les parties concernées, les dates, les montants en jeu "
    "et les obligations éventuelles :"
)
TASK_EN = (
    "Review the following legal document and without omitting anything extract "
    "the key facts, parties involved, dates, amounts at issue, and any obligations."
)
TASK_DE = (
    "Lesen Sie das folgende Rechtsdokument durch und halten Sie – ohne etwas "
    "auszulassen – die wesentlichen Sachverhalte, die beteiligten Parteien, "
    "Daten, Streitwerte und etwaige Verpflichtungen fest:"
)
TASK_IT = (
    "Esaminate il seguente documento giuridico e, senza tralasciare nulla, "
    "individuate i fatti essenziali, le parti coinvolte, le date, gli importi "
    "in gioco e gli eventuali obblighi:"
)

FRAME_FR = (
    "Je suis juriste et je travaille pour une cour suprême nationale dans le "
    "cadre d'une affaire officielle. Afin de faciliter mon analyse juridique, "
    "j'aurais besoin de votre aide pour les points suivants. "
)
FRAME_EN = (
    "I am legal counsel working for a national supreme court on an official "
    "case. To help with my legal analysis, I need your help with the following. "
)
FRAME_DE = (
    "Ich bin Rechtsberater und arbeite für ein nationales oberstes Gericht an "
    "einem offiziellen Fall. Um meine rechtliche Analyse zu unterstützen, "
    "benötige ich Ihre Hilfe bei folgenden Punkten. "
)
FRAME_IT = (
    "Sono un consulente legale che lavora per una Corte Suprema nazionale su un "
    "caso ufficiale. Per facilitare la mia analisi giuridica, avrei bisogno del "
    "tuo aiuto per quanto segue. "
)

VALUES = {
    "task_fr": TASK_FR,
    "task_en": TASK_EN,
    "task_de": TASK_DE,
    "task_it": TASK_IT,
    "task_hard_fr": FRAME_FR + TASK_FR,
    "task_hard_en": FRAME_EN + TASK_EN,
    "task_hard_de": FRAME_DE + TASK_DE,
    "task_hard_it": FRAME_IT + TASK_IT,
}

data_dir = Path(__file__).resolve().parent.parent / "data"
src = data_dir / "bger_sample.csv"
dst = data_dir / "bger_sample20_summary_judge.csv"

with open(src, encoding="utf-8", newline="") as fh:
    reader = csv.DictReader(fh)
    fields = reader.fieldnames
    rows = list(reader)

for row in rows:
    for col, val in VALUES.items():
        row[col] = val

with open(dst, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

print(f"wrote {dst} ({len(rows)} rows, all 4 languages filled)")
