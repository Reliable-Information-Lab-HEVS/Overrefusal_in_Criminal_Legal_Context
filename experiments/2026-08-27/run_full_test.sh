#!/usr/bin/env bash
#
# orbench_violence800_answer: FULL TEST
#
# 800 prompts x 4 models x 2 prefixes = 6400 generations. Long-running --
# run the smoke test first (run_smoke_test.sh) to confirm the environment
# works before spending a SLURM allocation on this.
#
# ---- SLURM ----------------------------------------------------------------
# This is a plain bash script with #SBATCH directives, so it can be
# submitted directly:
#   sbatch experiments/2026-08-27/run_full_test.sh
# TODO fill these in for your cluster -- these are placeholders, not real
# values (partition/account names, GPU resource name, and the time limit
# all vary per cluster):
#
#SBATCH --job-name=orbench_violence800_answer
#SBATCH --output=experiments/2026-08-27/results/slurm_%j.out
#SBATCH --error=experiments/2026-08-27/results/slurm_%j.err
#SBATCH --partition=TODO_partition_name
#SBATCH --account=TODO_account_name
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=24:00:00        # TODO: no throughput data yet for this
                                # hardware -- the smoke test's per-request
                                # time x 6400 is your best early estimate;
                                # pad generously, incremental output means
                                # a timeout doesn't lose completed rows.
#
# Also runs fine without a scheduler, e.g. inside tmux on an interactive
# allocation:
#   tmux new -s orbench_full_2026-08-27
#   bash experiments/2026-08-27/run_full_test.sh
# -----------------------------------------------------------------------------

set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

CSV_PATH="data/orbench_violence800_new.csv"
OUT_DIR="experiments/2026-08-27/results"
MODELS_DIR="${FULL_OLLAMA_MODELS_DIR:-$HOME/ollama_full_models}"
LOG="$OUT_DIR/ollama_server.log"

MODELS=(
  "llama3.1:8b"
  "qwen3:8b"
  "gemma4:e4b"
  "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M"
)
PREFIXES=("answer-armasuisse" "answer-analyst")

mkdir -p "$OUT_DIR" "$MODELS_DIR"

echo "=== 1. Pick a free port ==="
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
URL="http://127.0.0.1:${PORT}/api/generate"
echo "  using port $PORT"

echo "=== 2. Start private Ollama server ==="
# No CUDA_VISIBLE_DEVICES override here -- SLURM's --gres=gpu:1 above (or
# your own env, if run outside SLURM) already controls which GPU(s) are
# visible to this job. If you ever see an "offloaded 0/N layers to GPU"
# line in $LOG, that means Ollama silently fell back to CPU -- check
# `nvidia-smi` / `CUDA_VISIBLE_DEVICES` before assuming the run is just
# slow (this happened on another box in this project: see CLAUDE.md's
# "current work in progress" section).
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

echo "=== 6. Pull the 4 models into OUR OWN verified server ==="
for m in "${MODELS[@]}"; do
  echo "  pulling $m ..."
  OLLAMA_HOST="127.0.0.1:${PORT}" ollama pull "$m"
done

echo "=== 7. Run both prefixes (English, all 800 prompts) ==="
for prefix in "${PREFIXES[@]}"; do
  echo "--- prefix: $prefix ---"
  python3 run.py --prompts-file "$CSV_PATH" \
    --languages en --prefix "$prefix" \
    --ollama-url "$URL" \
    --incremental-output "$OUT_DIR/orbench_violence800_${prefix}_incremental.csv" \
    --output "$OUT_DIR/orbench_violence800_${prefix}.csv"
done

echo "=== 8. Keyword-only refusal summary ==="
python3 helpers/refusal_summary.py \
  "$OUT_DIR/orbench_violence800_answer-armasuisse.csv" \
  "$OUT_DIR/orbench_violence800_answer-analyst.csv" \
  --output "$OUT_DIR/refusal_summary.txt"

echo "=== 9. Stop the private Ollama server ==="
kill "$SERVER_PID" 2>/dev/null || true

echo "ALL DONE."
echo "  results  : $OUT_DIR/orbench_violence800_<prefix>.csv"
echo "  summary  : $OUT_DIR/refusal_summary.txt"
