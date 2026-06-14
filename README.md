# Authority Prefixes Trigger Over-refusal in Small Open-Weight LLMs

Anonymous code and data for the paper
*LLMs Prompted for Legal Context Object More: Overrefusal from Small On-Premises LLMs in Criminal Legal Context.*

## TL;DR

We test whether adding an unverifiable claim of professional or institutional
authority (e.g. *"I am legal counsel working for a national supreme court…"*) to
a benign prompt changes the refusal behavior of small open-weight LLMs.

Across four models (Llama 3.1 8B, Gemma 4 E4B, Qwen 3 8B, Apertus 8B), five
OR-Bench categories (violence, sexual, harmful, illegal, unethical) and three
languages (English, French, German), **authority prefixes consistently
*increase* refusal**, often 2–20×, the opposite of what one might expect.

Everything runs **on-premises** via [Ollama](https://ollama.com). No API keys.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

ollama pull llama3.1:8b
ollama pull qwen3:8b
ollama pull gemma4:e4b
ollama pull hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M
```

All models run locally with temperature 0, no system prompt, Ollama defaults.

## Pipeline

```
run.py --prefix …   →   results/*.csv   →   unify.py   →   master_long.csv   →   heatmap.py / table_frde.py
```

The prefix condition is injected **at run time** with `--prefix`
(`none` / `lawyer` / `supreme-court` / `jailbreak`), per language, from
`over_refusal/prefixes.py`. The same base prompt file is reused for every
condition — no need to pre-build prefixed CSVs.

### Run the evaluation

```bash
# one topic, English, supreme-court prefix
python run.py \
  --prompts-file data/orbench_violence200.csv \
  --languages en \
  --prefix supreme-court \
  --output orbench_violence200_supreme.csv
```

Full English run (5 topics × 4 conditions, all four models — models default to
the four above):

```bash
for topic in violence sexual harmful unethical illegal; do
  for prefix in none lawyer supreme-court jailbreak; do
    python run.py --prompts-file data/orbench_${topic}200.csv \
      --languages en --prefix ${prefix} \
      --output orbench_${topic}200_${prefix}.csv
  done
done
```

French/German (baseline vs supreme-court only):

```bash
for topic in violence sexual harmful unethical illegal; do
  for prefix in none supreme-court; do
    python run.py --prompts-file data/orbench_${topic}200.csv \
      --languages fr de --prefix ${prefix} \
      --output orbench_${topic}200_${prefix}_frde.csv
  done
done
```

### Build the master table and the figures

```bash
python helpers/unify.py        # merge all result CSVs -> results/master_long.csv
python helpers/table_frde.py   # print the French/German table (paper Table 1)
python helpers/heatmap.py      # render heatmap_english.png/.pdf
```

`results/master_long.csv` is the single long-format source of truth
(`model, lang, topic, prefix, prompt_id, is_refused`). `heatmap.py` holds the
published English figure values inline so the figure stays pinned to the paper.

## Refusal detection

Keyword matching only (method of Cui et al., 2025), extended with French and
German keyword lists derived from native model outputs. See
`over_refusal/detector.py` and `over_refusal/data/refusal_keywords.json`.
Detection scans only the opening of each response.

The released CSVs already contain a precomputed `is_refused` column, so all
tables/figures reproduce directly from the data. Note: `response_full` is empty
for some early-batch rows; the response text for those is in `response_preview`
(500 chars, enough for the opening-window detector).

## Data

```
data/
├── orbench_<topic>200.csv   # 200 OR-Bench prompts per category (fr/de/it/en text)
├── bger_sample.csv          # 20 real Swiss Federal Tribunal cases
├── US_sample.csv            # 10 documents from the public "Epstein Files" set
├── template_input.csv       # blank template for your own documents
└── INPUT_FORMAT.md          # how to fill it
```

OR-Bench prompts are the first 200 per category from the OR-Bench-80K release.
To run on your own confidential documents, fill `data/template_input.csv` and
pass it with `--prompts-file` (see `data/INPUT_FORMAT.md`). The text stays on
your machine; only aggregated refusal counts are produced.

## Repository layout

```
over_refusal/     pipeline (Ollama client, prefixes, detector, runner)
helpers/          unify.py, table_frde.py, heatmap.py, extract_orbench.py,
                  translate_prompts.py, compare*.py, summary_frde.py
data/             prompt CSVs (see above)
results/
├── english/        English runs (4 prefixes)
├── french_german/  FR/DE runs (+ refusal_matrices/ audit files)
├── real_text/      bger + US (Epstein) real-document runs
└── master_long.csv unified long-format results
```

## License

Code: MIT. OR-Bench prompts keep their original CC-BY-4.0 license.
