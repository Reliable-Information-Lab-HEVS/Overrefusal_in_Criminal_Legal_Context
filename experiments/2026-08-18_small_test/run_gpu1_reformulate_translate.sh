#!/usr/bin/env bash
# Run weapons_corridor_prompts.csv through 4 prefixes (reformulate x
# armasuisse/professional, translate-fr x armasuisse/professional) on all 4
# models, on GPU1 only via a private Ollama server instance.
#
# Unlike the earlier swiss_defense_summarization script, this one picks a
# fresh OS-assigned free port and explicitly verifies (via `ss -ltnp`) that
# OUR OWN process is the one bound to it before proceeding -- last time we
# silently ended up talking to francois.brouchou's already-running private
# instance because port 11435 happened to already be his.

set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

CSV_PATH="experiments/2026-08-18/data/weapons_corridor_prompts.csv"
OUT_DIR="experiments/2026-08-18/results"
GPU1_MODELS_DIR="$HOME/ollama_gpu1_models"   # reuse models already pulled here
GPU1_LOG="$OUT_DIR/ollama_gpu1_server.log"

mkdir -p "$OUT_DIR"

echo "=== 1. Pick a genuinely free port ==="
GPU1_PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
GPU1_URL="http://127.0.0.1:${GPU1_PORT}/api/generate"
echo "  using port $GPU1_PORT"

echo "=== 2. Start private Ollama server on GPU1 ==="
CUDA_VISIBLE_DEVICES=1 OLLAMA_HOST="127.0.0.1:${GPU1_PORT}" OLLAMA_MODELS="$GPU1_MODELS_DIR" \
  ollama serve > "$GPU1_LOG" 2>&1 &
GPU1_SERVER_PID=$!
echo "  spawned pid: $GPU1_SERVER_PID"

echo "=== 3. Wait for it to answer ==="
for i in $(seq 1 30); do
  if curl -s "http://127.0.0.1:${GPU1_PORT}/api/tags" > /dev/null 2>&1; then
    echo "  answering after ${i}s"
    break
  fi
  sleep 1
done

echo "=== 4. Verify OUR process actually owns this port (not someone else's server) ==="
OWNER_PID=$(ss -ltnp 2>/dev/null | grep -P ":${GPU1_PORT}\s" | grep -oP 'pid=\K[0-9]+' | head -1)
if [ "$OWNER_PID" != "$GPU1_SERVER_PID" ]; then
  echo "  ABORT: port $GPU1_PORT is owned by pid=$OWNER_PID, not our spawned pid=$GPU1_SERVER_PID."
  echo "  Refusing to proceed against a server we don't control. Killing our own spawn and exiting."
  kill "$GPU1_SERVER_PID" 2>/dev/null || true
  exit 1
fi
echo "  confirmed: pid $GPU1_SERVER_PID owns port $GPU1_PORT"

echo "=== 5. Sanity check GPU placement ==="
nvidia-smi --query-gpu=index,name,memory.used --format=csv

echo "=== 5b. Pull the 4 models into OUR OWN verified server (this dir was empty) ==="
MODELS=(
  "llama3.1:8b"
  "qwen3:8b"
  "gemma4:e4b"
  "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M"
)
for m in "${MODELS[@]}"; do
  echo "  pulling $m ..."
  OLLAMA_HOST="127.0.0.1:${GPU1_PORT}" ollama pull "$m"
done

echo "=== 6. Run all 4 prefixes ==="
run_one () {
  local prefix=$1 lang=$2
  echo "--- prefix: $prefix (lang=$lang) ---"
  python3 run.py --prompts-file "$CSV_PATH" \
    --languages "$lang" --prefix "$prefix" \
    --ollama-url "$GPU1_URL" \
    --output "$OUT_DIR/weapons_corridor_${prefix}_gpu1.csv"
}
run_one reformulate-armasuisse en
run_one reformulate-professional en
run_one translate-fr-armasuisse fr
run_one translate-fr-professional fr

echo "=== 7. Summary table ==="
python3 helpers/refusal_summary.py \
  "$OUT_DIR/weapons_corridor_reformulate-armasuisse_gpu1.csv" \
  "$OUT_DIR/weapons_corridor_reformulate-professional_gpu1.csv" \
  "$OUT_DIR/weapons_corridor_translate-fr-armasuisse_gpu1.csv" \
  "$OUT_DIR/weapons_corridor_translate-fr-professional_gpu1.csv" \
  --output "$OUT_DIR/refusal_summary.txt"

echo "=== 8. Stop the private GPU1 Ollama server ==="
kill "$GPU1_SERVER_PID" 2>/dev/null || true

echo "ALL DONE. Results in $OUT_DIR/"
