# Input format (scenario contract)

The tool reads **one CSV file**, **one row per case**. Every input source — the
OR-Bench category files, the BGer/real-text samples, and your own cases — uses
the same header:

```
prompt_id,or_category,bger_source,bger_url,task_fr,task_hard_fr,task_de,task_hard_de,task_it,task_hard_it,task_en,task_hard_en,orginal_language,text_fr,text_de,text_it,text_en
```

You do **not** pre-build prefixed files: the authority/jailbreak prefix is added
at run time with `--prefix` (see the main README), so the same base file is
reused for every condition.

## Column contract

`<lang>` is one of `fr`, `de`, `it`, `en`.

| Column | Required? | Meaning | Example |
|--------|-----------|---------|---------|
| `prompt_id` | **required** | Unique id for the case. | `tf_2024_001` |
| `or_category` | **required** | Topic label used to group/filter results. Any string. | `illegal` |
| `text_<lang>` | **required** (≥ 1 language) | The case text in that language. At least one `text_<lang>` must be non-empty. | `Le 12 mars, A. a été prévenu de vol…` |
| `task_<lang>` | optional | Instruction prepended to the text in that language. Final prompt is `task + "\n\n" + text`. Empty ⇒ the text is sent as-is. | `Résumez le document suivant :` |
| `task_hard_<lang>` | optional (legacy) | Old way of baking a prefix into the task. **Leave empty** — use `--prefix` instead. | *(empty)* |
| `bger_source` | optional | Provenance label. | `OR-Bench-80k` |
| `bger_url` | optional | Provenance URL. | *(empty)* |
| `orginal_language` | optional | Source language, informational only (column name keeps its historical spelling). | `fr` |

**Tolerant loader.** Missing *optional* columns are fine — the Federal Tribunal
will often supply only one or two languages and no `task_hard_*`. A row missing
a *required* field (`prompt_id`, `or_category`, or any text) is **skipped with a
warning**, not silently turned into an empty prompt.

## How the Federal Tribunal adds its own cases

1. Copy the template: `cp data/sample_TF.csv data/tf_cases.csv`.
2. Replace the single `tf_example_01` row with one row per case. Fill
   `prompt_id`, `or_category`, and the case text in **at least one** language
   (`text_fr` / `text_de` / `text_it` / `text_en`). Add a `task_<lang>`
   instruction if you want one (e.g. a summary request). Leave everything else
   empty.
3. Run it — the documents never leave the machine; only aggregated refusal
   counts are written:

   ```bash
   python run.py --prompts-file data/tf_cases.csv --ollama-only --languages fr de
   python run.py --prompts-file data/tf_cases.csv --ollama-only --languages fr de --prefix supreme-court
   ```

The file must be **UTF-8** encoded, and each `prompt_id` must be unique. See
[`sample_TF.csv`](sample_TF.csv) for a working one-row example.
