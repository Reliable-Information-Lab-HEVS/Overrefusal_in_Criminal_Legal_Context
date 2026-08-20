# Input format for the over-refusal tool

The tool reads **one CSV file**, one row per case. To evaluate your own
documents (e.g. internal Federal Tribunal cases that cannot be shared), copy
[`template_input.csv`](template_input.csv), fill in your rows, and point the
tool at it:

```bash
python run.py --prompts-file data/my_cases.csv --languages fr de it
```

You do **not** need to pre-build prefixed files. The authority/jailbreak prefix
is added at run time with `--prefix` (see the main README). So the same base
file is reused for every condition:

```bash
python run.py --prompts-file data/my_cases.csv --prefix none           # baseline
python run.py --prompts-file data/my_cases.csv --prefix supreme-court   # authority
```

## Two ways to run

- **Sample data (ours):** use the files already in `data/` (`orbench_*200.csv`,
  `bger_sample.csv`, `US_sample.csv`). Nothing to fill in — these reproduce the
  paper.
- **Your own data:** fill in `template_input.csv` with your cases. The text
  never leaves your machine; only the aggregated refusal counts are produced.

## Columns

| Column | Required? | Meaning |
|--------|-----------|---------|
| `prompt_id` | **yes** | Unique id for the case (e.g. `tf_2024_001`). |
| `or_category` | **yes** | Topic label used to group results (e.g. `illegal`, `violence`, or your own). |
| `task_fr` / `task_de` / `task_it` / `task_en` | **yes** (≥1 lang) | The instruction given to the model in that language (e.g. *"Summarize the following document"*). Leave a language empty to skip it. |
| `text_fr` / `text_de` / `text_it` / `text_en` | **yes** (same langs) | The case text in that language. The final prompt is `task + text`. |
| `orginal_language` | optional | The source language of the document (informational only; the column name keeps its historical spelling). |
| `bger_source` / `bger_url` | optional | Provenance metadata; safe to leave empty. |
| `task_hard_fr` / `task_hard_de` / … | optional (legacy) | Old way of baking a prefix into the task. **Leave empty** — use `--prefix` instead. |

## Rules

- One row = one case. Give every row a unique `prompt_id`.
- Only fill the languages you want to test. The tool runs whichever languages
  you pass to `--languages` and skips a case that has no text for a language.
- The file must be UTF-8 encoded.
- The two `<...>` placeholders in `template_input.csv` are just hints — replace
  them with real text or delete the example row.
