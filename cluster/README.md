# Cluster migration: armasuisse Slurm + Apptainer

Reproduces this repo's OR-Bench (English + French/German) and real-BGer-
judgment experiments on the armasuisse GPU cluster (`gpu-login1.intlab.ch`,
A100-PCIe-40GB, driver 595.71.05, CUDA 13.2, Ubuntu 24.04 nodes), migrating
off the old single-RTX-4090/system-Ollama setup described in the rest of
this repo's `CLAUDE.md`.

## Files

```
cluster/
├── apptainer/overrefusal.def   the environment (Ollama + pinned Python venv)
└── slurm/
    ├── pull_models.sh          one-time model warm-up (run first, alone)
    ├── run_experiments.sh      GPU job array: generation + LLM-judge pass
    ├── run_stats.sh            CPU job: McNemar/Holm-Bonferroni + figures
    ├── concat_csv.py           safe multi-CSV concat (used by run_experiments.sh)
    └── build_judge_master_long.py  rebuilds a legacy aggregate judge file
```

## 1. Build the container

**Never on the login node** (strict resource limits there — this is exactly
what `Sinteractive` is for):

```bash
ssh <username>@gpu-login1.intlab.ch
Sinteractive --gres=gpu:a100:1        # uses --qos interactive
mkdir -p ~/containers
cd ~/Overrefusal_in_Criminal_Legal_Context   # this repo, on $HOME (persistent)
apptainer build --fakeroot ~/containers/overrefusal.sif cluster/apptainer/overrefusal.def
```

`--fakeroot` is the standard unprivileged-build path on Apptainer clusters
that support it (no real root/sudo needed). If your account isn't set up
for `--fakeroot` (check `apptainer build --fakeroot` doesn't error with a
subuid/subgid message), the fallback is a remote build via Sylabs Cloud
(`apptainer build --remote ...`, needs a Sylabs account/token) — ask the
cluster admins which is enabled here if `--fakeroot` doesn't work.

The container does **not** contain the repo code, only Ollama + the pinned
Python environment. The repo itself stays a normal checkout under `$HOME`
and gets bind-mounted in automatically (Apptainer binds `$HOME` by default).
This means editing the Python pipeline doesn't require rebuilding the
container.

## 2. Warm up the model cache (once)

```bash
sbatch cluster/slurm/pull_models.sh
squeue -u $USER   # wait for it to finish
```

Downloads all 5 models (4 evaluated + the `qwen2.5:14b` judge model, ~20GB
total per the migration brief) into the persistent `$HOME/.ollama/models`
store, so `run_experiments.sh`'s 6 array tasks don't each try to pull the
same models concurrently into the same directory (a real race — see that
script's own header for why it deliberately does NOT pull models itself).

If you'd rather stage the model store on node-local `/scratch` for faster
loads, set `OLLAMA_MODELS_DIR=/scratch/$USER/ollama_models` when submitting
both `pull_models.sh` and `run_experiments.sh` — but then you're
responsible for `rm -rf` on that path at the end of your session, since
`/scratch` is fast but **not auto-cleaned**. The default here is `$HOME`
(persistent, backed up, and per the cluster's own guidance the shared NFS
is fast enough that `/scratch` is only worth it for the model store
specifically) — start there and only move to `/scratch` if a real run shows
model-load time actually matters.

## 3. Run the experiments (GPU, job array)

```bash
sbatch cluster/slurm/run_experiments.sh
squeue -u $USER
```

`run_experiments.sh` has placeholder `#SBATCH` values (`--mem`, `--time`,
`--qos`) marked `TODO` in its header — **fill those in for your account
before submitting**, and see "Right-sizing" below for how to do that from
real data instead of guessing.

It's a 6-task array:
- tasks 0–4: one OR-Bench topic each (violence/sexual/harmful/unethical/
  illegal) — English (4 prefixes) + French/German (2 prefixes), all 4
  models, plus an LLM-judge pass over every resulting CSV
- task 5: the real BGer paragraph arm, one output file per model (matching
  this repo's existing `results/real_text/bger_para/<model>.csv` naming)

Each task starts its own private Ollama server on a free, OS-assigned port
with its own model directory pointer, and verifies its own spawned process
actually owns that port before proceeding — the same defensive pattern used
elsewhere in this repo, after a past incident of a job accidentally reusing
someone else's already-running server on a hardcoded port.

Results land directly in this repo's existing `results/english/`,
`results/french_german/`, `results/judge/`, and `results/real_text/`
layout, so the downstream scripts in step 4 need no path changes.

**Test task 0 alone first**, not the whole array, to catch a broken build
or a wrong QOS/time limit cheaply:

```bash
sbatch --array=0-0 cluster/slurm/run_experiments.sh
```

### Right-sizing `--mem`/`--time` with `seff`

Once a task finishes (even just task 0), check its actual resource usage
before submitting the full array or future runs:

```bash
seff <jobid>
```

This reports actual memory high-water-mark and wall-clock time used against
what was requested. The `--time=08:00:00` / `--mem=64G` in
`run_experiments.sh` are unvalidated guesses (there's no A100 throughput
data yet for this pipeline) — use `seff` after the first real task to set
sane values for the rest, and remember the cluster backfills shorter jobs
sooner, so there's a real cost to over-padding `--time` beyond what `seff`
justifies.

### Job array rationale, and a further optimization

Splitting by topic (this script) parallelizes 5 independent prompt files
across whatever GPU allocation the cluster gives you concurrently, instead
of running them one sbatch call at a time. A further, unimplemented
optimization: splitting by **model** instead of (or in addition to) topic
would let each array task hold exactly one model resident for its entire
run, avoiding the per-prompt model-swap/reload overhead of Ollama serving 4
models in rotation from one server (this repo's `over_refusal/evaluation.py`
loops prompt × language × model, so a single-topic task still cycles
through all 4 models per prompt). `run.py --ollama-models <model>` already
supports this — see how task 5 (BGer) does it — if you want to restructure
the OR-Bench arm's array to be topic×model (20 tasks) instead of just topic
(5 tasks), that flag is the building block.

## 4. Run the stats (CPU only)

**After the full array (all 6 tasks) has finished:**

```bash
sbatch cluster/slurm/run_stats.sh
```

No `--gres` at all, so it queues on the CPU partition/QOS cheaply. It:
1. rebuilds `results/LLM-as-a-judge-final-aggregated-results/
   judge_master_long.csv` from this run's judge CSVs — see
   `build_judge_master_long.py`'s docstring for why this file needs
   regenerating at all: `results/english/mcnemar_analysis.py` and
   `results/french_german/mcnemar_analysis.py` are already published with
   the paper and hard-depend on this exact (originally hand-exported,
   oddly-formatted) file, so it's reproduced byte-for-byte in that same
   format rather than changing those two already-reviewed scripts.
2. runs `helpers/unify.py` → `results/master_long.csv`
3. runs whichever of `mcnemar_analysis.py` / `holm_bonferroni.py` exist in
   `results/english/`, `results/french_german/`, `results/real_text/`
4. runs `helpers/judge_agreement.py` and `helpers/final_refusal.py`
5. regenerates the figures/tables (`helpers/heatmap.py`,
   `helpers/table_frde.py`, `helpers/table_realtext.py`)

## Known gaps / things to verify on first real use

- **`--qos`**: both scripts default to `--qos normal`, matching the
  cluster's own minimal example, but that example is a 1-minute CPU job.
  Confirm `normal` actually permits an 8-hour GPU batch job on your
  account before relying on it (`sacctmgr show qos` or ask the cluster
  admins); `--qos interactive` is for `Sinteractive` only, not batch.
- **`--fakeroot` availability**: assumed but not confirmed for this
  account — see step 1.
- **No A100 throughput numbers yet**: every `--time`/`--mem` value in both
  Slurm scripts is a placeholder. Use `seff` after the first task (see
  above) before trusting them for the full run.
- **Model-swap overhead**: unlike the model-array optimization described
  above, the current topic-array design still cycles through all 4 models
  per prompt within a task, same as the old cluster. This didn't matter
  much for a small local test but caused real slowdowns on long-running
  jobs before (see the rest of this repo's `CLAUDE.md`, "current work in
  progress" — a job on the old cluster ended up running entirely on CPU for
  unrelated reasons, but the model-swap pattern is a separate, additive
  cost worth knowing about even once the GPU issue is fixed elsewhere).
- **Ollama version pin**: `overrefusal.def` pins `v0.33.1`, verified against
  its published `sha256sum.txt` at authoring time. Bump deliberately (with
  a new checksum) rather than silently, if you need a newer Ollama feature.

## Containerizing for other clusters?

If you need a similar `.def`/Slurm setup for a different cluster (different
GPU, different Slurm config, Docker instead of Apptainer, etc.), ask — the
approach here (bundle Ollama's own release tarball rather than a CUDA
toolkit, rely on `--nv`/the container runtime's own driver-passthrough for
GPU access, bind-mount the repo rather than baking it in, pin Python deps
via `uv`) generalizes, but exact base images/flags would need adjusting for
that cluster's specifics.
