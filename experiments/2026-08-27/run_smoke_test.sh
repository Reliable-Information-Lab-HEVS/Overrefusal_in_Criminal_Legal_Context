#!/usr/bin/env bash
# orbench_violence800_answer: SMOKE TEST
#
# 3 prompts x 4 models x 2 prefixes = 24 generations. Meant to finish in
# minutes and confirm the environment actually works (Ollama reachable,
# the 4 models pullable/pulled, over_refusal importable, prefixes.py has
# the answer-armasuisse/answer-analyst entries) before spending SLURM time
# on run_full_test.sh's 6400 generations.
#
# Run directly, no scheduler needed:
#   tmux new -s smoke_2026-08-27
#   bash experiments/2026-08-27/run_smoke_test.sh
# (or `srun --pty bash` into an interactive allocation first if your
# cluster's login node has no GPU / no outbound network for model pulls).
#
# Starts its OWN private Ollama server on a free, OS-assigned port with its
# own model directory -- does not touch any Ollama server you already have
# running. Verifies its own spawned PID actually owns the port it picked
# before proceeding (see CLAUDE.md: a prior run on another box once reused
# a colleague's already-running server on a hardcoded port by accident).

set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

CSV_PATH="data/orbench_violence800_new.csv"
OUT_DIR="experiments/2026-08-27/results"
MODELS_DIR="${SMOKE_OLLAMA_MODELS_DIR:-$HOME/ollama_smoke_models}"
LOG="$OUT_DIR/ollama_server_smoke.log"
SMOKE_LIMIT=3

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
# No CUDA_VISIBLE_DEVICES override here -- let SLURM's --gres allocation (or
# your shell env, if run outside SLURM) decide which GPU(s) are visible.
# Override by exporting CUDA_VISIBLE_DEVICES yourself before calling this
# script if you need to pin a specific device.
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
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi
echo "  confirmed: pid $SERVER_PID owns port $PORT"

echo "=== 5. Pull the 4 models into OUR OWN verified server ==="
for m in "${MODELS[@]}"; do
  echo "  pulling $m ..."
  OLLAMA_HOST="127.0.0.1:${PORT}" ollama pull "$m"
done

echo "=== 6. Run both prefixes (English, $SMOKE_LIMIT prompts) ==="
for prefix in "${PREFIXES[@]}"; do
  echo "--- prefix: $prefix ---"
  python3 run.py --prompts-file "$CSV_PATH" \
    --languages en --prefix "$prefix" --limit "$SMOKE_LIMIT" \
    --ollama-url "$URL" \
    --incremental-output "$OUT_DIR/orbench_violence800_${prefix}_smoke_incremental.csv" \
    --output "$OUT_DIR/orbench_violence800_${prefix}_smoke.csv"
done

echo "=== 7. Keyword refusal summary ==="
python3 helpers/refusal_summary.py \
  "$OUT_DIR/orbench_violence800_answer-armasuisse_smoke.csv" \
  "$OUT_DIR/orbench_violence800_answer-analyst_smoke.csv" \
  --output "$OUT_DIR/refusal_summary_smoke.txt"

echo "=== 8. Stop the private Ollama server ==="
kill "$SERVER_PID" 2>/dev/null || true

echo "SMOKE TEST DONE."
echo "  results  : $OUT_DIR/orbench_violence800_<prefix>_smoke.csv"
echo "  summary  : $OUT_DIR/refusal_summary_smoke.txt"
echo "If this looks right, submit run_full_test.sh next."
