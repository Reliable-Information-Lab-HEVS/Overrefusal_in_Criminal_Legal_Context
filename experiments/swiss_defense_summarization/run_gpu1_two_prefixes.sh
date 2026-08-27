#!/usr/bin/env bash
# Merge experiments/swiss_defense_summarization/data/*.txt into a fresh CSV
# and run it through all 4 models under two prefixes (extract-armasuisse,
# extract-professional), on GPU1 only.
#
# GPU1-only is enforced by running a SECOND, private Ollama server (our own
# user, own port, own model copies under ~/ollama_gpu1) with
# CUDA_VISIBLE_DEVICES=1 -- that process cannot see GPU0 at all, so nothing
# it loads can land there. This does not touch the shared system Ollama
# server on port 11434 (owned by the `ollama` user; we don't have
# permission to read its model store anyway), so it won't disturb anyone
# else's job on GPU0.
#
# Run inside tmux so it survives closing the laptop:
#   tmux new -s swiss_defense_gpu1
#   bash experiments/swiss_defense_summarization/run_gpu1_two_prefixes.sh
#   (detach with Ctrl+b d; reattach later with: tmux attach -t swiss_defense_gpu1)

set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

DATA_DIR="experiments/swiss_defense_summarization/data"
OUT_DIR="experiments/swiss_defense_summarization/results/gpu1_run"
CSV_PATH="$DATA_DIR/swiss_defense_docs.csv"
GPU1_PORT=11435
GPU1_URL="http://127.0.0.1:${GPU1_PORT}/api/generate"
GPU1_MODELS_DIR="$HOME/ollama_gpu1_models"
GPU1_LOG="$OUT_DIR/ollama_gpu1_server.log"

MODELS=(
  "llama3.1:8b"
  "qwen3:8b"
  "gemma4:e4b"
  "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M"
)
PREFIXES=("extract-armasuisse" "extract-professional")

mkdir -p "$OUT_DIR" "$GPU1_MODELS_DIR"

echo "=== 1. Merge $DATA_DIR/*.txt -> $CSV_PATH ==="
python3 helpers/txt_files_to_csv.py "$DATA_DIR" swiss_defense "$CSV_PATH"

echo "=== 2. Start private Ollama server on GPU1 (port $GPU1_PORT) ==="
CUDA_VISIBLE_DEVICES=1 OLLAMA_HOST="127.0.0.1:${GPU1_PORT}" OLLAMA_MODELS="$GPU1_MODELS_DIR" \
  ollama serve > "$GPU1_LOG" 2>&1 &
GPU1_SERVER_PID=$!
echo "  server pid: $GPU1_SERVER_PID (log: $GPU1_LOG)"

echo "=== 3. Wait for it to come up ==="
for i in $(seq 1 30); do
  if curl -s "http://127.0.0.1:${GPU1_PORT}/api/tags" > /dev/null 2>&1; then
    echo "  ready after ${i}s"
    break
  fi
  sleep 1
done

echo "=== 4. Pull the 4 models into the GPU1 instance (skips if already present) ==="
for m in "${MODELS[@]}"; do
  echo "  pulling $m ..."
  OLLAMA_HOST="127.0.0.1:${GPU1_PORT}" ollama pull "$m"
done

echo "=== 5. Sanity check: confirm this server only sees GPU1 ==="
nvidia-smi --query-gpu=index,name,memory.used --format=csv

echo "=== 6. Run both prefixes ==="
for prefix in "${PREFIXES[@]}"; do
  echo "--- prefix: $prefix ---"
  python3 run.py --prompts-file "$CSV_PATH" \
    --languages en --prefix "$prefix" --num-ctx 40960 \
    --ollama-url "$GPU1_URL" \
    --output "$OUT_DIR/swiss_defense_${prefix}_gpu1.csv"
done

echo "=== 7. Summary table ==="
python3 helpers/refusal_summary.py \
  "$OUT_DIR/swiss_defense_extract-armasuisse_gpu1.csv" \
  "$OUT_DIR/swiss_defense_extract-professional_gpu1.csv" \
  --output "$OUT_DIR/refusal_summary.txt"

echo "=== 8. Stop the private GPU1 Ollama server ==="
kill "$GPU1_SERVER_PID" 2>/dev/null || true

echo "ALL DONE. Results in $OUT_DIR/"
