#!/usr/bin/env bash
#
# orbench_violence800_answer: FULL TEST
#
# Default: 800 prompts x 4 models x 2 prefixes = 6400 generations.
# Long-running -- run run_smoke_test.sh FIRST and use its timing_smoke.txt
# output to set --time below realistically before submitting this.
#
# Runs inside the Apptainer container (cluster/apptainer/overrefusal.def)
# via the same self-re-exec pattern as cluster/slurm/run_experiments.sh --
# bare `ollama`/`python3` do not exist on this cluster outside the
# container.
#
#   sbatch experiments/2026-08-27/run_full_test.sh
#
# To run a SMALLER slice instead of all 800 (e.g. while still waiting on
# timing data, or to spend less GPU time), override FULL_CSV_PATH and
# RUN_LABEL together -- e.g. the pre-built 100-prompt slice
# (orbench_violence_204..303, deliberately NOT overlapping the 3 prompts
# run_smoke_test.sh already used at _201.._203):
#   FULL_CSV_PATH=data/orbench_violence100_new.csv RUN_LABEL=violence100 \
#     sbatch experiments/2026-08-27/run_full_test.sh
# Output filenames use RUN_LABEL, so a 100-prompt run and an 800-prompt run
# never collide or get confused with each other.
#
#SBATCH --job-name=orbench_violence800_answer
#SBATCH --output=experiments/2026-08-27/results/slurm_%j.out
#SBATCH --error=experiments/2026-08-27/results/slurm_%j.err
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=24:00:00        # TODO: set this from run_smoke_test.sh's
                                # timing_smoke.txt (per_generation_avg x 6400,
                                # padded), not left at this placeholder --
                                # observed early throughput on this A100 was
                                # ~4 tokens/sec for llama3.1:8b, which would
                                # make 6400 generations take far longer than
                                # 24h if that holds across all 4 models.
#SBATCH --qos=normal            # TODO: confirm this QOS allows a job this
                                # long on your account.
#
# Also runs fine without a scheduler, e.g. inside tmux on an interactive
# allocation:
#   tmux new -s orbench_full_2026-08-27
#   bash experiments/2026-08-27/run_full_test.sh
# -----------------------------------------------------------------------------

set -euo pipefail
# Resolve the repo root via SLURM_SUBMIT_DIR (always set by sbatch, to the
# directory it was invoked from), NOT $0 -- sbatch commonly copies a
# submitted batch script to a per-job spool file before executing it, so $0
# does not reliably point back to this file's real location in the repo
# under sbatch (a well-known Slurm gotcha; bit us in practice: $0-based
# resolution landed on an unwritable path and "mkdir -p experiments/..."
# failed with Permission denied). Falls back to the current directory for
# direct `bash script.sh` use -- run it from the repo root in that case,
# matching every usage example here.
REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"
SCRIPT_PATH="$REPO_ROOT/experiments/2026-08-27/run_full_test.sh"

CSV_PATH="${FULL_CSV_PATH:-data/orbench_violence800_new.csv}"
RUN_LABEL="${RUN_LABEL:-violence800}"
OUT_DIR="experiments/2026-08-27/results"
# Shared, persistent model store -- same one pull_models.sh / manual pulls
# already populated, so this doesn't re-download anything.
MODELS_DIR="${FULL_OLLAMA_MODELS_DIR:-$HOME/.ollama/models}"
LOG="$OUT_DIR/ollama_server.log"
SIF="${OVERREFUSAL_SIF:-$HOME/containers/overrefusal.sif}"

MODELS=(
  "llama3.1:8b"
  "qwen3:8b"
  "gemma4:e4b"
  "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M"
)
PREFIXES=("answer-armasuisse" "answer-analyst")

mkdir -p "$OUT_DIR" "$MODELS_DIR"

if [ -z "${INSIDE_APPTAINER_OVERREFUSAL:-}" ]; then
  export INSIDE_APPTAINER_OVERREFUSAL=1
  exec apptainer exec --nv --bind "$HOME:$HOME" --pwd "$REPO_ROOT" \
    "$SIF" bash "$SCRIPT_PATH" "$@"
fi

T_START=$(date +%s)

echo "=== 1. Pick a free port ==="
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
URL="http://127.0.0.1:${PORT}/api/generate"
echo "  using port $PORT"

echo "=== 2. Start private Ollama server (already inside the container) ==="
OLLAMA_HOST="127.0.0.1:${PORT}" OLLAMA_MODELS="$MODELS_DIR" \
  ollama serve > "$LOG" 2>&1 &
SERVER_PID=$!
echo "  spawned pid: $SERVER_PID"

echo "=== 3. Wait for it to answer ==="
for i in $(seq 1 30); do
  if curl -s "http://127.0.0.1:${PORT}/api/tags" > /dev/null 2>&1; then
    echo "  answering after ${i}s"
    break
  fi
  sleep 1
done

echo "=== 4. Verify OUR process actually owns this port ==="
OWNER_PID=$(ss -ltnp 2>/dev/null | grep -P ":${PORT}\s" | grep -oP 'pid=\K[0-9]+' | head -1)
if [ "$OWNER_PID" != "$SERVER_PID" ]; then
  echo "  ABORT: port $PORT is owned by pid=$OWNER_PID, not our spawned pid=$SERVER_PID."
  echo "  Refusing to proceed against a server we don't control."
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi
echo "  confirmed: pid $SERVER_PID owns port $PORT"

echo "=== 5. Sanity check GPU placement ==="
nvidia-smi --query-gpu=index,name,memory.used --format=csv 2>&1 || true

echo "=== 6. Verify all 4 models are already pulled ==="
# Deliberately NOT pulling here -- run this only after the models are
# already in $MODELS_DIR (they should be, from earlier manual pulls /
# pull_models.sh). Fails fast with a clear message instead of silently
# trying (and failing) to download mid-run.
MISSING=0
for m in "${MODELS[@]}"; do
  if ! OLLAMA_HOST="127.0.0.1:${PORT}" ollama list | grep -qF "$m"; then
    echo "  MISSING: $m"
    MISSING=1
  fi
done
if [ "$MISSING" -eq 1 ]; then
  echo "ABORT: pull the missing model(s) first (see run_smoke_test.sh's step 5 message)."
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi

N_PROMPTS=$(( $(wc -l < "$CSV_PATH") - 1 ))
echo "=== 7. Run both prefixes (English, $N_PROMPTS prompts from $CSV_PATH) ==="
for prefix in "${PREFIXES[@]}"; do
  echo "--- prefix: $prefix ---"
  T0=$(date +%s)
  python3 run.py --prompts-file "$CSV_PATH" \
    --languages en --prefix "$prefix" \
    --ollama-url "$URL" \
    --incremental-output "$OUT_DIR/${RUN_LABEL}_${prefix}_incremental.csv" \
    --output "$OUT_DIR/${RUN_LABEL}_${prefix}.csv"
  echo "  prefix $prefix took $(( $(date +%s) - T0 ))s ($N_PROMPTS x ${#MODELS[@]} = $(( N_PROMPTS * ${#MODELS[@]} )) generations)"
done

echo "=== 8. Keyword-only refusal summary ==="
python3 helpers/refusal_summary.py \
  "$OUT_DIR/${RUN_LABEL}_answer-armasuisse.csv" \
  "$OUT_DIR/${RUN_LABEL}_answer-analyst.csv" \
  --output "$OUT_DIR/refusal_summary_${RUN_LABEL}.txt"

echo "=== 9. Stop the private Ollama server ==="
kill "$SERVER_PID" 2>/dev/null || true

echo "ALL DONE. Total elapsed: $(( $(date +%s) - T_START ))s"
echo "  results  : $OUT_DIR/${RUN_LABEL}_<prefix>.csv"
echo "  summary  : $OUT_DIR/refusal_summary_${RUN_LABEL}.txt"
echo "Run 'seff \$SLURM_JOB_ID' (if submitted via sbatch) to check actual memory/time usage."
