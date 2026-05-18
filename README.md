# Over-Refusal Evaluation

Python pipeline to measure whether LLMs refuse legitimate prompts on
sensitive legal topics. Built on the methodology of OR-Bench
(Cui et al., ICML 2025, [arXiv:2405.20947](https://arxiv.org/abs/2405.20947)).

## What it does

1. Loads a CSV of Swiss Federal Court (BGer) cases, each with task instructions
   and case facts in 4 languages (FR, DE, IT, EN).
2. Sends prompts to multiple backends (local Ollama models + remote APIs).
3. Detects refusals with a fast keyword-matching pass (OR-Bench Appendix M).
4. Optionally re-classifies responses with an LLM-as-a-Judge ensemble
   (3-class taxonomy: `direct_answer` / `direct_refusal` / `indirect_refusal`,
   majority vote across GPT, Claude, Gemini).

## Project structure

```
over_refusal_eval_project/
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example                 # template, copy to .env (gitignored)
├── run.py                       # entry point
├── data/
│   └── bger_sample_0421_translated.csv
├── results/                     # run outputs (gitignored)
└── over_refusal/
    ├── __init__.py
    ├── config.py                # env keys + model defaults + paths
    ├── prompts.py               # CSV loader + filtering
    ├── detector.py              # keyword refusal detector
    ├── evaluation.py            # run loop + CLI
    ├── judge.py                 # LLM-as-a-Judge (OR-Bench, 3-class)
    ├── reporting.py             # printed summary tables
    ├── storage.py               # CSV writer
    ├── data/
    │   ├── refusal_keywords.json
    │   └── judge_prompt.txt
    └── clients/
        ├── base.py
        ├── ollama.py
        ├── mistral.py
        ├── openai_client.py
        ├── claude.py
        └── gemini.py
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## API keys

Keys are read from environment variables, never hardcoded.

```bash
cp .env.example .env
# edit .env and put your real keys in it
```

The code auto-loads `.env` if `python-dotenv` is installed (it is in
`requirements.txt`). Otherwise, export the variables manually:

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export MISTRAL_API_KEY=...
export GEMINI_API_KEY=...
```

`.env` is gitignored. Never commit real keys.

## Run

Quick smoke test (3 prompts, EN only, all backends):

```bash
python run.py --quick
```

API only, French only, both task variants (normal + hard):

```bash
python run.py --api-only --languages fr --task-mode all
```

Local Ollama only, all 4 languages:

```bash
python run.py --ollama-only --languages fr de it en
```

Filtered run (only "violence" cases, 2 prompts):

```bash
python run.py --categories violence --limit 2 --task-mode hard
```

Output filename:

```bash
python run.py --output bgr_full_run.csv
# saves to results/bgr_full_run.csv
```

By default results are written to `results/over_refusal_results_<timestamp>.csv`.

## LLM-as-a-Judge

After a run, classify the responses into the 3-class OR-Bench taxonomy:

```bash
python -m over_refusal.judge --input results/bgr_full_run.csv
```

Hybrid mode (skip LLM call on rows already flagged by keyword matching, faster):

```bash
python -m over_refusal.judge --input results/bgr_full_run.csv --only-ambiguous
```

Custom ensemble:

```bash
python -m over_refusal.judge --input results/bgr_full_run.csv --judges gpt claude
```

Adds 3 columns: `judge_label`, `judge_is_refusal`, `judge_votes`.

## Editing the data without touching code

- Refusal keywords: `over_refusal/data/refusal_keywords.json`
- Judge prompt template: `over_refusal/data/judge_prompt.txt`
- Prompts dataset: `data/bger_sample_0421_translated.csv`

## Reference

Cui, J., Chiang, W.-L., Stoica, I., & Hsieh, C.-J. (2025).
*OR-Bench: An Over-Refusal Benchmark for Large Language Models.*
ICML 2025. [arXiv:2405.20947](https://arxiv.org/abs/2405.20947)
# Refusal_restricted_topics-aka-Tribunal-Federal-project-
