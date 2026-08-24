# Authority Prefixes Trigger Over-refusal in Small Open-Weight LLMs

Anonymous code and data for the paper
*LLMs Prompted for Legal Context Refuse More: Overrefusal from Small
On-Premises LLMs in Criminal Legal Context.*

## TL;DR

We test whether adding an unverifiable claim of professional or institutional
authority (e.g. *"I am legal counsel working for a national supreme court…"*) to
a benign prompt changes the refusal behavior of small open-weight LLMs.

Across four models (Llama 3.1 8B, Gemma 4 E4B, Qwen 3 8B, Apertus 8B), five
OR-Bench categories (violence, sexual, harmful, illegal, unethical) and three
languages (English, French, German), **authority prefixes consistently
*increase* refusal**, often 2–20×, the opposite of what one might expect. The
same effect holds on real Swiss Federal Supreme Court judgments (BGER) - 200 documents
selected by querying offense-specific terms restricted to the criminal-law dockets.

Everything runs **on-premises** via [Ollama](https://ollama.com). No API keys,
except optionally DeepL when rebuilding the translated datasets.

## The two experiments

| | prompts | languages | prefix conditions | results |
|---|---|---|---|---|
| **OR-Bench** | 200 per category × 5 categories | en, fr, de | none, lawyer, supreme-court, jailbreak (en) / none, supreme-court (fr, de) | `results/english/`, `results/french_german/`, `results/master_long.csv` |
| **BGer judgments** | 1 652 fact paragraphs from 200 judgments | en, fr, de | none, supreme-court | `results/real_text/` |

## Models

The paper evaluates exactly these four, all served locally with temperature 0,
no system prompt and Ollama defaults:

```bash
ollama pull llama3.1:8b
ollama pull qwen3:8b
ollama pull gemma4:e4b
ollama pull hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M
ollama pull qwen2.5:14b     # judge only, not evaluated
```

Earlier rounds of this project also ran `gemma3:4b` and `qwen2.5:7b`. Those runs
are **not** part of this release: every number and every file here comes from
the four models above.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the evaluation

```
run.py --prefix …  →  results/*.csv  →  unify.py  →  master_long.csv  →  figures/tables
                   ↘  run_judge.py   →  results/judge/*.csv
```

The prefix condition is injected **at run time** with `--prefix`
(`none` / `lawyer` / `supreme-court` / `jailbreak`), per language, from
`over_refusal/prefixes.py`. The same base prompt file is reused for every
condition — no need to pre-build prefixed CSVs.

Sanity-check the whole pipeline in a few seconds (3 prompts, English only):

```bash
python run.py --prompts-file data/orbench_violence200.csv --quick
```

Full English run (5 topics × 4 conditions, all four models):

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

Real legal texts, paragraph by paragraph. The released runs used `--task-mode
all`, which emits both the plain instruction (`task_<lang>`, baseline) and the
instruction with the prefix already in it (`task_hard_<lang>`, supreme-court):

```bash
python run.py --prompts-file data/bger_para200.csv \
  --languages en fr de --task-mode all \
  --output bger_para200.csv
```

`--prefix supreme-court` on the baseline task is the run-time equivalent and
gives the same wording, joined with a blank line instead of a space.

## Tables and figures

```bash
python helpers/unify.py           # merge OR-Bench result CSVs -> results/master_long.csv
python helpers/heatmap.py         # English heatmap (paper Figure 1)
python helpers/table_frde.py      # French/German table (paper Table 1)
python helpers/table_realtext.py  # BGer paragraph table (paper Table 2)
python helpers/judge_agreement.py # keyword vs judge, per language and model
```

`results/master_long.csv` is the single long-format source of truth for the
OR-Bench arm (`model, lang, topic, prefix, prompt_id, is_refused`).

## Refusal detection


Response is considered as refused if either it's classified ''directly refused'' 
by an LLM-as-a-judge(Qwen2.5:14b, [results/judge/](results/judge/)) or by keyword-matching OR-Bench method,
that was extended with French and German keyword lists manually refined by 
native-speakers authors of the paper. See
`over_refusal/detector.py` and `over_refusal/data/refusal_keywords.json`.

Keyword matching (method of Cui et al., 2025), extended with French and German
keyword lists derived from native model outputs rather than translation. 
Detection scans only the opening of each response.

Every released CSV already carries a precomputed `is_refused` column, so all
tables and figures reproduce directly from the data, without a GPU.

## Statistical tests

To check whether an authority-framing prefix actually shifts refusal
behavior rather than reflecting noise, we pair each prompt's baseline
(`none`) response with its response under a prefix and run McNemar's exact
test (one-sided: does the prefix increase refusals), then apply a
Holm-Bonferroni correction across all tests run within each language family,
since we run one test per model/language/prefix combination. This is done
separately for the English OR-Bench arm, the French/German OR-Bench arm, and
the real BGer paragraph arm. See
[results/mcnemar_summary.md](results/mcnemar_summary.md) for the full
write-up and result tables, and the `mcnemar_analysis.py` /
`holm_bonferroni.py` scripts with their `mcnemar_appendix.csv` outputs in
[results/english/](results/english/), [results/french_german/](results/french_german/),
and [results/real_text/](results/real_text/) for the underlying pipeline and
numbers.

## Data

```
data/
├── orbench_<topic>200.csv   200 OR-Bench prompts per category (fr/de/it/en)
├── bger_full200.csv         200 Swiss Federal Supreme Court judgments, facts only
├── bger_para200.csv         the same judgments split into 1 652 paragraphs (192 judgments)
├── bger_sample.csv          the first 20 judgments, evaluated as whole documents
├── US_sample.csv            10 documents from the public "Epstein Files" set
├── template_input.csv       blank template for your own documents
└── INPUT_FORMAT.md          how to fill it
```

Every prompt file uses the same columns: `task_<lang>` (instruction),
`task_hard_<lang>` (instruction with the supreme-court prefix baked in), and
`text_<lang>` (the document or question). To run on your own confidential
documents, fill `data/template_input.csv` and pass it with `--prompts-file`. The
text stays on your machine; only aggregated refusal counts are produced.

### Rebuilding the datasets

OR-Bench prompts (first 200 per category of the OR-Bench-80K release):

```bash
for topic in violence sexual harmful unethical illegal; do
  python helpers/extract_orbench.py ${topic} data/orbench_${topic}200.csv 200
done
python helpers/translate_prompts.py          # DeepL, key from .env
```

Swiss Federal Supreme Court corpus:

```bash
python helpers/bger_scrape.py --out data/bger_full200.csv --target 180
python helpers/bger_translate.py --in data/bger_full200.csv --out data/bger_full200.csv
python helpers/split_paragraphs.py --csv data/bger_full200.csv --write
```

`bger_scrape.py` queries the public AZA collection of bger.ch with
offense-specific terms in French and German (never article numbers — the same
number means different things in different Swiss statutes), keeps criminal-law
dockets, extracts the facts section, and deduplicates by reference and by
content. `bger_translate.py` fills the missing language columns from the
judgment's own source language; the DeepL key is read from `DEEPL_API_KEY` (see
`.env.example`) and is never written to any output file.

`split_paragraphs.py` keeps a judgment only if its four language versions have
the same number of paragraphs: 192 of the 200 judgments qualify, giving the
1 652 line-aligned paragraphs used in the paper. The 8 excluded judgments and
the language where each one diverges are printed by the script.

## Repository layout

```
over_refusal/     pipeline (Ollama client, prefixes, detector, runner)
run.py            run an evaluation
run_judge.py      LLM-as-a-judge pass over a result CSV
helpers/          data collection, unification, tables, figures
data/             prompt and document CSVs (see above)
results/
├── english/        OR-Bench English runs (4 prefixes), refusal_summary_english.*,
│                   mcnemar_analysis.py / mcnemar_results.csv (McNemar test)
├── french_german/  OR-Bench FR/DE runs (+ refusal_matrices/ audit files),
│                   refusal_summary_french_german.*, mcnemar_analysis.py /
│                   holm_bonferroni.py / mcnemar_appendix.csv
├── real_text/
│   ├── bger_para/    BGer paragraph runs, one CSV per model
│   ├── bger_sample.csv   the 20 judgments as whole documents
│   ├── US_sample.csv     "Epstein Files" documents
│   └── mcnemar_analysis.py / holm_bonferroni.py / mcnemar_appendix.csv
│                       McNemar/Holm-Bonferroni test, BGer paragraph arm
├── judge/          LLM-as-a-judge labels: orbench.csv (OR-Bench, all langs),
│                   bger_para/, bger_sample.csv, US_sample.csv
├── LLM-as-a-judge-final-aggregated-results/judge_master_long.csv
│                   long-format judge labels for OR-Bench, used by the
│                   McNemar and refusal-summary scripts above
├── master_long.csv unified OR-Bench results (keyword detector only)
├── mcnemar_appendix.csv, holm_bonferroni.py   English McNemar/Holm-Bonferroni test
└── mcnemar_summary.md   write-up combining all three statistical-test arms
paraphrasing_test/  robustness of the effect to prefix rewording (paper appendix)
```

## License

Code: MIT. OR-Bench prompts keep their original CC-BY-4.0 license. BGer
judgments are public Swiss case law.
