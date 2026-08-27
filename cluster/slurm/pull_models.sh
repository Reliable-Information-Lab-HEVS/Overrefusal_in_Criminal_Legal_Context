#!/bin/bash
# One-time model warm-up: pulls all 5 models (4 evaluated + the judge model)
# into the persistent, shared $HOME/.ollama/models store, ONCE, before the
# run_experiments.sh array is submitted.
#
# Why this is a separate job: run_experiments.sh's array tasks (see
# --array=0-5 there) all point OLLAMA_MODELS at the SAME shared $HOME
# directory so the ~20GB of models are downloaded once, not once per task
# (per the migration brief). But if multiple array tasks each ran their own
# `ollama pull` concurrently against that same first-populated store, their
# writes to the same manifest/blob files could race. Running this once,
# alone, first, then submitting the array only afterwards, avoids that
# entirely -- the array tasks' own `ollama pull` calls become simple no-op
# hash checks against an already-complete store.
#
# No GPU needed for this step -- pulling is just network + disk I/O.
#
#SBATCH --job-name=overrefusal_pull_models
#SBATCH --output=cluster/slurm/logs/pull_models_%j.out
#SBATCH --error=cluster/slurm/logs/pull_models_%j.err
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --qos=normal

set -euo pipefail
# SLURM_SUBMIT_DIR (always set by sbatch, to the directory it was invoked
# from), NOT $0 -- sbatch commonly copies a submitted batch script to a
# per-job spool file before executing it, so $0 does not reliably point
# back to this file's real location in the repo under sbatch (confirmed in
# practice on a sibling script using the same $0-based pattern: it caused
# a silent "Permission denied" trying to create a directory under the
# wrong, spool-derived path). Falls back to the current directory for
# direct `bash script.sh` use -- run it from the repo root in that case.
cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
mkdir -p cluster/slurm/logs

SIF="${OVERREFUSAL_SIF:-$HOME/containers/overrefusal.sif}"
OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-$HOME/.ollama/models}"
mkdir -p "$OLLAMA_MODELS_DIR"

MODELS=(
  "llama3.1:8b"
  "qwen3:8b"
  "gemma4:e4b"
  "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M"
  "qwen2.5:14b"   # judge model only, not itself evaluated
)

echo "=== Pick a free port ==="
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")

echo "=== Start private Ollama server (container) ==="
apptainer exec --bind "$HOME:$HOME" \
  --env OLLAMA_HOST="127.0.0.1:${PORT}",OLLAMA_MODELS="$OLLAMA_MODELS_DIR" \
  "$SIF" ollama serve > "cluster/slurm/logs/pull_models_server_${SLURM_JOB_ID:-local}.log" 2>&1 &
SERVER_PID=$!

echo "=== Wait for it to answer ==="
for i in $(seq 1 30); do
  if curl -s "http://127.0.0.1:${PORT}/api/tags" > /dev/null 2>&1; then
    echo "  answering after ${i}s"
    break
  fi
  sleep 1
done

echo "=== Verify OUR process owns this port ==="
# Runs on the bare host here (this script never re-execs into the
# container -- only the ollama calls below go through apptainer exec), so
# a missing `ss` would mean iproute2 isn't on the node itself, not a
# container packaging gap -- different fix than the container-side check
# in run_experiments.sh/run_smoke_test.sh/run_full_test.sh.
if ! command -v ss >/dev/null 2>&1; then
  echo "ABORT: 'ss' not found on this node (needs iproute2 installed on the host)."
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi
OWNER_PID=$(ss -ltnp 2>/dev/null | grep -P ":${PORT}\s" | grep -oP 'pid=\K[0-9]+' | head -1) || true
if [ "$OWNER_PID" != "$SERVER_PID" ]; then
  echo "ABORT: port $PORT owned by pid=$OWNER_PID, not our pid=$SERVER_PID."
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi

echo "=== Pull all 5 models into $OLLAMA_MODELS_DIR ==="
for m in "${MODELS[@]}"; do
  echo "  pulling $m ..."
  apptainer exec --bind "$HOME:$HOME" \
    --env OLLAMA_HOST="127.0.0.1:${PORT}",OLLAMA_MODELS="$OLLAMA_MODELS_DIR" \
    "$SIF" ollama pull "$m"
done

kill "$SERVER_PID" 2>/dev/null || true
echo "DONE. Models are cached in $OLLAMA_MODELS_DIR -- safe to submit run_experiments.sh now."
