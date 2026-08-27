# CLAUDE.md

Background for working in this repo so it doesn't need re-explaining each session.

## What this project is

Anonymous code/data release for a paper on **over-refusal in small open-weight
LLMs in criminal-legal contexts**: does prepending an unverifiable claim of
professional/institutional authority (e.g. "I am legal counsel working for a
national supreme court...") to a benign prompt change a model's refusal
behavior? Finding: authority prefixes usually *increase* refusal (2–20x),
the opposite of the naive expectation.

Everything runs **on-premises via Ollama** — no API keys, no cloud calls.
Four models tested: `llama3.1:8b`, `qwen3:8b`, `gemma4:e4b`,
`hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M`. Temperature 0,
no system prompt, Ollama defaults. Languages: fr/de/it (Swiss official) + en.

Full usage instructions are in [README.md](README.md) — this file is
architecture/context, not a how-to.

## Pipeline

```
run.py --prefix …  →  results/*.csv  →  helpers/unify.py  →  results/master_long.csv  →  helpers/heatmap.py / table_frde.py
```

`run.py` just delegates to `over_refusal.evaluation.main()`.

### `over_refusal/` package

- **`evaluation.py`** — `EvaluationRunner`, the CLI/orchestrator. Triple loop:
  prompt × language × model. For each: loads prompt text (falls back to `en`
  if the target language is missing), applies the prefix via
  `prefixes.apply_prefix`, sends it through `OllamaClient.query`, runs
  `RefusalDetector.is_refusal`, and appends a result row. `--incremental-output`
  writes each row to disk immediately (crash-safety for long runs), separate
  from the final CSV written by `main()`.
- **`prefixes.py`** — central registry of all prefix conditions (see below).
  This is the main extension point: **add a new experiment condition by
  adding one dict entry here, not by pre-baking new CSVs.**
- **`prompts.py`** — loads the prompts CSV. Expects columns `prompt_id,
  or_category, task_{lang}, task_hard_{lang}, text_{lang}` (task_hard is
  legacy — prefer `--prefix` instead of baking prefixes into a task column).
  `task_mode`: `normal` / `hard` / `all`.
- **`detector.py`** — `RefusalDetector`, pure keyword matching (method of Cui
  et al. 2025 / OR-Bench), keywords in `over_refusal/data/refusal_keywords.json`
  (en/fr/de/it). Only scans the **opening 300 chars** of the response
  (`OPENING_WINDOW_CHARS`) to avoid false positives from refusal-like phrases
  appearing later as quoted content in otherwise-compliant long answers.
  English keywords are always checked too, as a fallback for models that
  answer in English regardless of prompt language.
- **`clients/ollama.py`** — `OllamaClient`, thin wrapper over
  `POST /api/generate`, temperature 0, optional `num_ctx`. Returns
  `"[ERROR] {exc}"` on failure rather than raising (so a run degrades to
  error rows instead of crashing).
- **`storage.py`** — `ResultSaver`: `save_csv` (final output) and
  `append_row` (incremental, opens/flushes per call).
- **`config.py`** — Ollama URL/timeout/model list, supported languages,
  default paths. No API keys anywhere (on-prem only).

### Helpers (`helpers/`)

- `unify.py` — merges all result CSVs into `results/master_long.csv`
  (`model, lang, topic, prefix, prompt_id, is_refused`), the single
  long-format source of truth for figures/tables.
- `table_frde.py`, `heatmap.py` — paper figures/tables. `heatmap.py` pins the
  published English figure values inline (doesn't recompute from CSVs), so
  it stays fixed even if new runs are added later.
- `refusal_summary.py` — reusable per-model refusal-count table (n / refused
  / errors / rate) for any `run.py`-shaped CSV. Takes multiple CSVs at once;
  `--output` writes a `.txt` alongside stdout. Used by most `experiments/*`
  scripts to generate their `SUMMARY.txt`.
- `txt_files_to_csv.py` — merges a folder of raw `.txt` documents into a
  minimal prompts CSV (`prompt_id, or_category, bger_source,
  orginal_language, text_en`), English-only. Used to turn a folder of real
  documents (e.g. defense white papers) into something `run.py` can consume.
- `extract_orbench.py`, `translate_prompts.py` — regenerate
  `data/orbench_*200.csv` from scratch (OR-Bench-80K + DeepL).
- `compare4.py`, `compare_any.py`, `summary_frde.py` — analysis/comparison
  scripts over result CSVs.

## The prefix system (main extensibility point)

`over_refusal/prefixes.py` holds `PREFIXES: Dict[condition -> Dict[lang -> text]]`.
`apply_prefix(prompt_text, condition, lang)` prepends the right wording (falls
back to the English wording if a language is missing for that condition) and
joins with `\n\n`. `condition="none"` is the no-prefix baseline.

**To add a new prefix condition: add one entry to `PREFIXES` and it's
immediately available via `--prefix <name>` everywhere — no new CSVs needed.**

Current families:

| Family | Conditions | Purpose |
|---|---|---|
| Paper conditions | `none`, `lawyer`, `supreme-court`, `jailbreak` | Original paper wordings, all 4 languages |
| Institutional-affiliation triple | `analyst` (control, "myself") / `armasuisse` (military — Swiss defense procurement agency) / `kindergarten` (civilian control) | Matched minimal pairs — identical wording except the affiliation noun. Isolates the effect of *which* institution is claimed, not just "any authority claim". English only so far. |
| Extraction task variants | `extract-{armasuisse,professional,library}` and `extract2-{armasuisse,professional,library}` | Same affiliation triple, closing on an extraction instruction instead of "help me with the following" — used with long real documents (`swiss_defense_summarization`) or short prompts (`extract2`, used by `weapons_huggingface`, `cbrn_first_filter`) |
| Answer-task pair | `answer-armasuisse` / `answer-analyst` | Same pair, closing on "answer and explain" — used for multiple-choice-style prompts (`cbrn_harmful`) |
| Reformulate/translate pairs | `reformulate-{armasuisse,professional}`, `translate-fr-{armasuisse,professional}` | Same pair, different task wording, used on short prompts (`weapons_corridor`). **Gotcha:** `translate-fr-*` must be run with `--languages fr` — the loader falls back to English text since `text_fr` is empty, but this makes `evaluation.py` score the (French) output against the French keyword list. Running it as `en` would score French output against English keywords. |

When extending the institutional-affiliation idea to a new task or dataset,
follow the existing naming pattern: `<task>-<affiliation>`, and keep the
wording identical across the affiliation variants within a family except for
the institution noun — that matched-pair structure is what makes the
comparison valid (isolates one variable).

FR/DE/IT wordings for the affiliation-triple families **do not exist yet** —
only `supreme-court`, `lawyer`, `jailbreak` are translated. Adding non-English
wordings to `analyst`/`armasuisse`/`kindergarten` (and dependents) is
pending work if those experiments need to run outside English.

## Data & results layout

```
data/                        canonical prompt sets (versioned)
├── orbench_<topic>200.csv     200 OR-Bench prompts/category, fr/de/it/en, CC-BY-4.0
├── bger_sample.csv            20 real Swiss Federal Tribunal cases
├── US_sample.csv               10 "Epstein Files" documents
├── template_input.csv         blank template — see data/INPUT_FORMAT.md
results/
├── english/                   4-prefix English runs (paper)
├── french_german/              baseline vs supreme-court, fr/de (+ refusal_matrices audit files)
├── real_text/                  bger + US real-document runs
└── master_long.csv             unified long-format source of truth (from unify.py)
experiments/                  newer/exploratory runs, one subfolder per experiment:
├── orbench_violence_authority_prefixes/   analyst vs armasuisse (violence topic)
├── orbench_violence_kindergarten/         + kindergarten as a 3rd affiliation
├── swiss_defense_summarization/           extract-{armasuisse,professional} on real
│                                            defense white papers (data/*.txt merged
│                                            via txt_files_to_csv.py)
├── cbrn_first_filter/, cbrn_harmful/, transluce_cbrn/, weapons_huggingface/
│                                          extraction/answer variants on CBRN &
│                                            weapons-related prompt sets
└── 2026-08-18*/                           weapons_corridor prompts, reformulate/
                                             translate-fr conditions
```

Each mature experiment folder tends to contain: the input CSV (or a
`data/*.txt` folder + a merge script), one result CSV per condition, a
`refusal_summary.txt` (from `helpers/refusal_summary.py`), and a `SUMMARY.txt`
write-up (method, file manifest, results table, key finding, caveats,
"pending / not yet run" section). Follow that structure for new experiments —
the SUMMARY.txt convention is what lets a folder be understood without
re-running anything.

### Running a second Ollama instance on GPU1

Several experiment scripts (`experiments/swiss_defense_summarization/run_gpu1_two_prefixes.sh`,
`experiments/2026-08-18_small_test/run_gpu1_reformulate_translate.sh`) spin up
a **private, second Ollama server** pinned to GPU1 via
`CUDA_VISIBLE_DEVICES=1`, its own port, and its own model store
(`~/ollama_gpu1_models`), then point `run.py` at it with `--ollama-url`. This
lets a run proceed on GPU1 without touching the shared system Ollama server
on GPU0 (owned by a different user in some environments). The newer script
picks an OS-assigned free port and **verifies via `ss -ltnp` that its own
spawned PID actually owns that port** before proceeding — a prior run
accidentally reused a colleague's already-running private instance on a
hardcoded port. Prefer the free-port + ownership-check pattern for any new
GPU1 script.

## Cluster migration: armasuisse Slurm + Apptainer

Branch `slurm-apptainer-migration` (not yet merged) adds a `cluster/`
directory that reproduces the OR-Bench + real-BGer experiments on a
separate Slurm+Apptainer cluster (`gpu-login1.intlab.ch`, A100-PCIe-40GB,
Ubuntu 24.04 nodes) instead of this repo's usual single-RTX-4090/system-
Ollama setup. See `cluster/README.md` for the full build/submit
walkthrough; short version:

```
cluster/
├── apptainer/overrefusal.def   Ollama (bundled GPU backends, no CUDA
│                                toolkit needed — Apptainer's --nv binds the
│                                host driver at runtime) + a Python venv with
│                                pinned datasets/fsspec/huggingface_hub
│                                (fixes a "fsspec glob '**' invalid pattern"
│                                failure hit on an old Python-3.8 cluster)
└── slurm/
    ├── pull_models.sh          one-time model warm-up (avoids a real
    │                            concurrent-`ollama pull` race across the
    │                            job array below, since all tasks share one
    │                            $HOME/.ollama/models store)
    ├── run_experiments.sh      GPU job array (--array=0-5): one OR-Bench
    │                            topic per task (0-4) + the real-BGer arm
    │                            (5, one output file per model, matching
    │                            results/real_text/bger_para/'s existing
    │                            per-model naming). Re-execs itself inside
    │                            the container so `python3 run.py` actually
    │                            picks up the pinned venv, not the host's.
    ├── run_stats.sh             CPU-only: McNemar/Holm-Bonferroni + figures
    ├── concat_csv.py            safe multi-CSV concat (never cat/tail —
    │                            response fields contain embedded newlines)
    └── build_judge_master_long.py
                                  rebuilds results/LLM-as-a-judge-final-
                                  aggregated-results/judge_master_long.csv,
                                  a file with no producing script in this
                                  repo (it's a hand spreadsheet export —
                                  nested CSV: an inner RFC4180 row treated as
                                  one field of an outer semicolon-delimited
                                  export) that results/english/
                                  mcnemar_analysis.py and results/
                                  french_german/mcnemar_analysis.py both
                                  hard-depend on. Reproduced byte-for-byte
                                  in that format rather than touching those
                                  two already-published analysis scripts.
```

Also added on this branch: `scipy` to `requirements.txt` (a real,
previously-undeclared dependency of `results/*/mcnemar_analysis.py`'s
`scipy.stats.binomtest` import).

Known gaps as of authoring: no A100 throughput numbers yet (the Slurm
scripts' `--time`/`--mem` are unvalidated placeholders — right-size with
`seff <jobid>` after a first real task), `--fakeroot` build-permission
unconfirmed for this account, and the OR-Bench arm still cycles through all
4 models per prompt within a topic task (a further per-model array split,
like the BGer task 5 already does via `--ollama-models <model>`, would
avoid that reload overhead but isn't implemented). See `cluster/README.md`'s
"Known gaps" section for details.

## Known gotchas / conventions

- `--num-ctx` should be set explicitly (e.g. `40960`) for long documents to
  avoid silent truncation — Ollama's default context window is small.
  `swiss_defense_summarization` uses this.
- CSV field size limit is raised in `prompts.py` at import time (needed for
  long real-document text in a single `text_*` cell).
- `is_error` rows (network/timeout failures, `"[ERROR] ..."` responses) are
  real failures, not refusals — exclude them from refusal-rate analysis
  (`refusal_summary.py` reports them separately but still includes them in
  `n` for the rate denominator; check which convention a given script uses).
- Refusal detection is intentionally simple keyword matching, not an LLM
  judge — consistent with the paper's method, but known to have occasional
  false positives (e.g. an answer that opens with "Filing an X is illegal,
  unethical..." can be flagged as a refusal). Flag suspicious rows for manual
  review rather than silently trusting `is_refused` when exact counts matter.
- No API keys needed for the core pipeline. `.env` / `DEEPL_API_KEY` is only
  for `helpers/translate_prompts.py` (regenerating prompt translations), not
  for running evaluations.

## Current work in progress (as of 2026-08-26)

The `experiments/orbench_violence_authority_prefixes/` (analyst vs
armasuisse) and `experiments/orbench_violence_kindergarten/` (+ kindergarten)
results together form a 3-way matched-affiliation comparison on the
`violence` OR-Bench topic, English only. This is being expanded — see that
folder's SUMMARY.txt "pending" sections for the known next steps (more
topics, FR/DE/IT wordings, resolving the one suspected false-positive row).
