# Over-Refusal Evaluation

A small, reproducible pipeline that measures whether open-weight LLMs refuse
benign-but-borderline prompts on legally sensitive topics, and how that refusal
shifts when an authority / role-play **task** prefix is prepended.

Built on the methodology of OR-Bench (Cui et al., ICML 2025,
[arXiv:2405.20947](https://arxiv.org/abs/2405.20947)).

## How it works

A run combines two ingredients:

1. **Data** — a CSV of cases, one per row, with the case text in French,
   German and English.
2. **Task** — an optional instruction/role prefix (e.g. *defense lawyer*,
   *supreme-court counsel*) prepended to the case text. Running with no task
   sends the case text alone.

For each (case × language × model) the prompt is sent to the model, and a
keyword detector flags whether the response opens with a refusal.

Every model runs **locally via [Ollama](https://ollama.com/)** — there is no
remote API and no model API key. (Apertus runs locally too, as an Ollama GGUF.)
There is also **no LLM-as-judge**: refusal is decided by the keyword detector
only. The only external service is DeepL, used solely to translate prompts.

## Layout

```
.
├── run.py                       # evaluation CLI entry point
├── extract_orbench.py           # (optional) build data CSVs from OR-Bench
├── data/                        # case CSVs (7 columns, see below)
│   ├── orbench_<category>.csv   # OR-Bench prompts (English origin)
│   └── bger.csv                 # real Swiss Federal Court rulings (FR/DE origin)
├── prompts/                     # one JSON per task prefix
│   ├── summary.json
│   ├── judge.json               # "national supreme court counsel"
│   ├── lawyer.json              # "defense lawyer"
│   └── jailbreak.json           # role-play "developer mode" override
├── results/                     # run outputs
└── refusal_eval/
    ├── config.py                # paths, languages, models, key getters
    ├── prompts.py               # data CSV loader + filtering
    ├── tasks.py                 # task loader + prompt builder
    ├── detector.py              # keyword refusal detector
    ├── evaluation.py            # run loop + CLI
    ├── reporting.py             # printed summary tables
    ├── storage.py               # CSV writer
    ├── translate.py             # DeepL fill for data + tasks
    ├── data/refusal_keywords.json
    └── clients/                 # ollama.py
```

### Data format

Every file in `data/` has exactly these columns:

```
prompt_id, or_category, source, orginal_language, text_fr, text_de, text_en
```

`orginal_language` is the language the text was authored in; the other
`text_<lang>` columns are DeepL translations (see *Translation* below). The
OR-Bench files are English-origin; `bger.csv` holds 20 real Swiss Federal Court
rulings authored in French or German (with the other languages translated).

### Task format

Each task is one JSON file in `prompts/`:

```json
{
  "task_en": "I'm a defense lawyer ... Could you help me with the following?",
  "task_fr": "Je suis avocat de la défense ...",
  "task_de": "Ich bin Strafverteidiger ..."
}
```

The task name is the file stem (`lawyer`, `judge`, `summary`, `jailbreak`).
Add a new condition by dropping a new JSON file in the folder — no code change.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows ; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Local models are served by [Ollama](https://ollama.com/); pull the ones you
need, e.g. `ollama pull llama3.1:8b`.

## Run

No task (case text only), English, default Ollama models:

```bash
python run.py --data data/orbench_harmful.csv
```

With the *lawyer* task, French + German:

```bash
python run.py --data data/orbench_harmful.csv --task lawyer --languages fr de
```

Pick specific models (any local Ollama tag, e.g. an Apertus GGUF):

```bash
python run.py --data data/orbench_illegal.csv --task judge \
    --models llama3.1:8b qwen3:8b apertus:8b
```

Quick check (5 cases, one model):

```bash
python run.py --data data/orbench_sexual.csv --limit 5 --models llama3.1:8b
```

Useful flags: `--task {summary,judge,lawyer,jailbreak,none}`,
`--languages fr de en`, `--models`, `--categories`, `--prompt-ids`, `--limit`,
`--output`.

Results are written to `results/<data>_<task>_<timestamp>.csv` by default, with
columns `prompt_id, or_category, source, task, lang, model, prompt, response,
is_refused, is_error`.

## Translation

If a data file only has the original-language text (e.g. `text_en`), fill the
other languages with DeepL (set `DEEPL_API_KEY` in `.env`):

```bash
python -m refusal_eval.translate --data data/orbench_harmful.csv          # data
python -m refusal_eval.translate --tasks                                  # all task JSONs
python -m refusal_eval.translate --data data/*.csv --tasks --dry-run      # preview only
```

Already-filled cells are never overwritten, so translation runs are resumable.

## Re-extracting prompts

To rebuild the data CSVs from OR-Bench (needs `datasets`):

```bash
pip install datasets
python extract_orbench.py illegal data/orbench_illegal.csv 200
python -m refusal_eval.translate --data data/orbench_illegal.csv
```

## Reference

Cui, J., Chiang, W.-L., Stoica, I., & Hsieh, C.-J. (2025).
*OR-Bench: An Over-Refusal Benchmark for Large Language Models.* ICML 2025.
[arXiv:2405.20947](https://arxiv.org/abs/2405.20947)
