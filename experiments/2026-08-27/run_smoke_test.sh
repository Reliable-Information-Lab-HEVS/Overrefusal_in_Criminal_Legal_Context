#!/usr/bin/env bash
# orbench_violence800_answer: SMOKE TEST
#
# 3 prompts x 4 models x 2 prefixes = 24 generations. Meant to finish in
# minutes and confirm the environment actually works (Ollama reachable,
# the 4 models pulled, over_refusal importable, prefixes.py has the
# answer-armasuisse/answer-analyst entries) AND -- just as importantly --
# to measure real per-generation timing so run_full_test.sh's #SBATCH
# --time isn't a guess. See timing_smoke.txt in the output dir after this
# finishes.
#
# Runs inside the Apptainer container (cluster/apptainer/overrefusal.def)
# via the same self-re-exec pattern as cluster/slurm/run_experiments.sh --
# bare `ollama`/`python3` do not exist on this cluster outside the
# container, only the container's pinned venv + bundled Ollama binary do.
#
# Submit as its own short Slurm job:
#   sbatch experiments/2026-08-27/run_smoke_test.sh
# or run directly inside an interactive session (Sinteractive
# --gres=gpu:a100:1), e.g. inside tmux:
#   tmux new -s smoke_2026-08-27
#   bash experiments/2026-08-27/run_smoke_test.sh
#
#SBATCH --job-name=orbench_violence800_smoke
#SBATCH --output=experiments/2026-08-27/results/slurm_smoke_%j.out
#SBATCH --error=experiments/2026-08-27/results/slurm_smoke_%j.err
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --qos=normal

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
SCRIPT_PATH="$REPO_ROOT/experiments/2026-08-27/run_smoke_test.sh"

CSV_PATH="data/orbench_violence800_new.csv"
OUT_DIR="experiments/2026-08-27/results"
# Shared, persistent model store -- reuses whatever's already been pulled
# manually (e.g. via earlier container testing) instead of re-downloading
# into a separate directory.
MODELS_DIR="${SMOKE_OLLAMA_MODELS_DIR:-$HOME/.ollama/models}"
LOG="$OUT_DIR/ollama_server_smoke.log"
SMOKE_LIMIT=3
SIF="${OVERREFUSAL_SIF:-$HOME/containers/overrefusal.sif}"

MODELS=(
  "llama3.1:8b"
  "qwen3:8b"
  "gemma4:e4b"
  "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M"
)
PREFIXES=("answer-armasuisse" "answer-analyst")

mkdir -p "$OUT_DIR" "$MODELS_DIR"

# Re-exec inside the container so ollama/python3 resolve to the pinned
# binary/venv instead of the (nonexistent) host versions. See
# cluster/slurm/run_experiments.sh for the same pattern.
if [ -z "${INSIDE_APPTAINER_OVERREFUSAL:-}" ]; then
  export INSIDE_APPTAINER_OVERREFUSAL=1
  exec apptainer exec --nv --bind "$HOME:$HOME" --pwd "$REPO_ROOT" \
    "$SIF" bash "$SCRIPT_PATH" "$@"
fi

TIMING_FILE="$OUT_DIR/timing_smoke.txt"
: > "$TIMING_FILE"
log_timing() { echo "$1: ${2}s" | tee -a "$TIMING_FILE"; }
T_START=$(date +%s)

echo "=== 1. Pick a free port ==="
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
URL="http://127.0.0.1:${PORT}/api/generate"
echo "  using port $PORT"

echo "=== 2. Start private Ollama server ==="
T0=$(date +%s)
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
log_timing "server_startup" "$(( $(date +%s) - T0 ))"

echo "=== 4. Verify OUR process actually owns this port ==="
if ! command -v ss >/dev/null 2>&1; then
  echo "  ABORT: 'ss' not found (needs iproute2 in the container -- rebuild"
  echo "  overrefusal.sif after pulling the latest cluster/apptainer/overrefusal.def)."
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi
OWNER_PID=$(ss -ltnp 2>/dev/null | grep -P ":${PORT}\s" | grep -oP 'pid=\K[0-9]+' | head -1) || true
if [ "$OWNER_PID" != "$SERVER_PID" ]; then
  echo "  ABORT: port $PORT is owned by pid=$OWNER_PID, not our spawned pid=$SERVER_PID."
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi
echo "  confirmed: pid $SERVER_PID owns port $PORT"

echo "=== 5. Check which models are present (not pulling here -- see README) ==="
# Lenient by design: runs with whatever's already pulled rather than
# aborting, so you're not blocked waiting on a slow model download (e.g.
# Apertus) to test the rest of the pipeline. Only fails if NONE are present.
T0=$(date +%s)
MODELS_TO_RUN=()
for m in "${MODELS[@]}"; do
  if OLLAMA_HOST="127.0.0.1:${PORT}" ollama list | grep -qF "$m"; then
    MODELS_TO_RUN+=("$m")
  else
    echo "  SKIPPING (not pulled yet): $m"
  fi
done
if [ "${#MODELS_TO_RUN[@]}" -eq 0 ]; then
  echo "ABORT: none of the 4 models are pulled yet. Pull at least one, e.g.:"
  echo "  apptainer exec --env OLLAMA_HOST=127.0.0.1:${PORT},OLLAMA_MODELS=$MODELS_DIR $SIF ollama pull <model>"
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi
echo "  running with: ${MODELS_TO_RUN[*]}"
log_timing "model_verify" "$(( $(date +%s) - T0 ))"

echo "=== 6. Run both prefixes (English, $SMOKE_LIMIT prompts, ${#MODELS_TO_RUN[@]}/${#MODELS[@]} models) ==="
for prefix in "${PREFIXES[@]}"; do
  echo "--- prefix: $prefix ---"
  T0=$(date +%s)
  python3 run.py --prompts-file "$CSV_PATH" \
    --languages en --prefix "$prefix" --limit "$SMOKE_LIMIT" \
    --ollama-models "${MODELS_TO_RUN[@]}" \
    --ollama-url "$URL" \
    --incremental-output "$OUT_DIR/orbench_violence800_${prefix}_smoke_incremental.csv" \
    --output "$OUT_DIR/orbench_violence800_${prefix}_smoke.csv"
  ELAPSED=$(( $(date +%s) - T0 ))
  N_GEN=$(( SMOKE_LIMIT * ${#MODELS_TO_RUN[@]} ))
  log_timing "prefix_${prefix}_total ($N_GEN generations, ${#MODELS_TO_RUN[@]} models)" "$ELAPSED"
  log_timing "prefix_${prefix}_per_generation_avg" "$(python3 -c "print(round($ELAPSED / $N_GEN, 1))")"
done

echo "=== 7. Keyword refusal summary ==="
python3 helpers/refusal_summary.py \
  "$OUT_DIR/orbench_violence800_answer-armasuisse_smoke.csv" \
  "$OUT_DIR/orbench_violence800_answer-analyst_smoke.csv" \
  --output "$OUT_DIR/refusal_summary_smoke.txt"

echo "=== 8. Stop the private Ollama server ==="
kill "$SERVER_PID" 2>/dev/null || true

TOTAL_ELAPSED=$(( $(date +%s) - T_START ))
log_timing "TOTAL_smoke_test" "$TOTAL_ELAPSED"

TOTAL_GEN=$(( SMOKE_LIMIT * ${#MODELS_TO_RUN[@]} * ${#PREFIXES[@]} ))
FULL_GEN=$(( 800 * ${#MODELS[@]} * ${#PREFIXES[@]} ))
echo "" | tee -a "$TIMING_FILE"
echo "Extrapolation hint: this smoke test ran $TOTAL_GEN generations with ${#MODELS_TO_RUN[@]}/${#MODELS[@]} models." | tee -a "$TIMING_FILE"
if [ "${#MODELS_TO_RUN[@]}" -lt "${#MODELS[@]}" ]; then
  echo "NOTE: this did not cover all models -- re-run once the rest are pulled before trusting" | tee -a "$TIMING_FILE"
  echo "the per-generation average for models not yet tested (they may differ in speed)." | tee -a "$TIMING_FILE"
fi
echo "The full run is $FULL_GEN generations (800 prompts x ${#MODELS[@]} models x ${#PREFIXES[@]} prefixes)." | tee -a "$TIMING_FILE"
echo "Use the per_generation_avg lines above (per prefix, since models differ in speed) to estimate" | tee -a "$TIMING_FILE"
echo "run_full_test.sh's --time -- do NOT just linearly scale the TOTAL_smoke_test line, since it" | tee -a "$TIMING_FILE"
echo "includes one-time server startup + model-load overhead that the full run only pays once too," | tee -a "$TIMING_FILE"
echo "but per-generation cost repeats. Pad generously for variance across models/prompts." | tee -a "$TIMING_FILE"

echo "SMOKE TEST DONE."
echo "  results  : $OUT_DIR/orbench_violence800_<prefix>_smoke.csv"
echo "  summary  : $OUT_DIR/refusal_summary_smoke.txt"
echo "  timing   : $TIMING_FILE"
echo "If this looks right, use the timing above to set run_full_test.sh's --time, then submit it."
