#!/bin/bash
# GPU generation job: reproduces the paper's OR-Bench (English + French/
# German) and real-BGer-judgment arms, via a Slurm job array.
#
# WHY AN ARRAY: the 5 OR-Bench topics (violence, sexual, harmful, unethical,
# illegal) are fully independent -- different prompt files, different output
# files, no shared state -- so they're natural array tasks rather than 5
# separate sbatch calls (the cluster docs recommend arrays over many sbatch
# calls). The BGer real-text arm is a 6th, different-shaped task (it already
# has its own upstream convention of one output file per model -- see
# results/real_text/bger_para/*.csv -- so it loops over the 4 models
# internally instead of over topics).
#
#   task 0-4: OR-Bench topics violence/sexual/harmful/unethical/illegal
#   task 5:   real BGer paragraphs (all 4 models, task-mode all)
#
# PREREQUISITE: run pull_models.sh ONCE first and wait for it to finish.
# This script does NOT pull models itself -- it only verifies they're
# present -- specifically to avoid concurrent-pull races across array tasks
# that all point at the same shared $HOME/.ollama/models store (see
# pull_models.sh's header for why).
#
# TODO before submitting -- fill in for your allocation:
#SBATCH --job-name=overrefusal_experiments
#SBATCH --output=cluster/slurm/logs/experiments_%A_%a.out
#SBATCH --error=cluster/slurm/logs/experiments_%A_%a.err
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=08:00:00        # TODO: no A100 throughput data yet for this
                                # pipeline -- this is a guess. Run task 0
                                # alone first (--array=0-0), then check
                                # `seff <jobid>` and right-size --mem/--time
                                # for the real array submission. Shorter
                                # requested times backfill sooner per the
                                # cluster docs, so don't pad blindly.
#SBATCH --qos=normal            # TODO: confirm this QOS allows 8h batch GPU
                                # jobs on your account (the docs' own example
                                # uses --qos normal for a 1-minute CPU job;
                                # --qos interactive is for Sinteractive only).
#SBATCH --array=0-5

set -euo pipefail
# Resolve the repo root via SLURM_SUBMIT_DIR (always set by sbatch, to the
# directory it was invoked from), NOT $0 -- sbatch commonly copies a
# submitted batch script to a per-job spool file before executing it, so $0
# does not reliably point back to this file's real location in the repo
# under sbatch (a well-known Slurm gotcha; bit us in practice: $0-based
# resolution landed on an unwritable path and "mkdir -p experiments/..."
# failed with Permission denied, in a sibling script using the same
# pattern). Falls back to the current directory for direct `bash script.sh`
# use -- run it from the repo root in that case, matching every usage
# example here.
REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"
SCRIPT_PATH="$REPO_ROOT/cluster/slurm/run_experiments.sh"
mkdir -p cluster/slurm/logs results/english results/french_german \
  results/real_text/bger_para results/judge/bger_para

SIF="${OVERREFUSAL_SIF:-$HOME/containers/overrefusal.sif}"
OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-$HOME/.ollama/models}"
JUDGE_MODEL="qwen2.5:14b"
CONCAT="cluster/slurm/concat_csv.py"

# Re-exec this entire script inside the container (--nv: bind the host's
# NVIDIA driver in) so every command below -- ollama, python3, the pinned
# venv -- runs in the container's environment, not the bare host shell.
# Without this, `python3 run.py` below would silently pick up whatever
# python3 happens to be on the compute node's PATH instead of the pinned
# datasets/scipy/etc. versions this container exists to guarantee.
if [ -z "${INSIDE_APPTAINER_OVERREFUSAL:-}" ]; then
  export INSIDE_APPTAINER_OVERREFUSAL=1
  export OLLAMA_MODELS_DIR SIF
  exec apptainer exec --nv --bind "$HOME:$HOME" --pwd "$REPO_ROOT" \
    "$SIF" bash "$SCRIPT_PATH" "$@"
fi

MODELS=(
  "llama3.1:8b"
  "qwen3:8b"
  "gemma4:e4b"
  "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M"
)
# Short names matching the existing results/real_text/bger_para/*.csv and
# results/judge/bger_para/*.csv convention already used in this repo.
declare -A SHORT_NAME=(
  ["llama3.1:8b"]="llama3.1-8b"
  ["qwen3:8b"]="qwen3-8b"
  ["gemma4:e4b"]="gemma4-e4b"
  ["hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M"]="apertus-8b"
)

echo "=== 1. Pick a free port ==="
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
URL="http://127.0.0.1:${PORT}/api/generate"
echo "  using port $PORT"

echo "=== 2. Start private Ollama server (already inside the container) ==="
OLLAMA_HOST="127.0.0.1:${PORT}" OLLAMA_MODELS="$OLLAMA_MODELS_DIR" \
  ollama serve > "cluster/slurm/logs/server_${SLURM_ARRAY_JOB_ID:-local}_${SLURM_ARRAY_TASK_ID:-0}.log" 2>&1 &
SERVER_PID=$!

echo "=== 3. Wait for it to answer ==="
for i in $(seq 1 30); do
  if curl -s "http://127.0.0.1:${PORT}/api/tags" > /dev/null 2>&1; then
    echo "  answering after ${i}s"; break
  fi
  sleep 1
done

echo "=== 4. Verify OUR process owns this port ==="
if ! command -v ss >/dev/null 2>&1; then
  echo "ABORT: 'ss' not found (needs iproute2 in the container -- rebuild"
  echo "overrefusal.sif after pulling the latest cluster/apptainer/overrefusal.def)."
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi
OWNER_PID=$(ss -ltnp 2>/dev/null | grep -P ":${PORT}\s" | grep -oP 'pid=\K[0-9]+' | head -1) || true
if [ "$OWNER_PID" != "$SERVER_PID" ]; then
  echo "ABORT: port $PORT owned by pid=$OWNER_PID, not our pid=$SERVER_PID."
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi
echo "  confirmed: pid $SERVER_PID owns port $PORT"

echo "=== 5. Sanity check GPU placement ==="
nvidia-smi --query-gpu=index,name,memory.used --format=csv 2>&1 || true

echo "=== 6. Verify all required models are already pulled ==="
# Deliberately NOT pulling here -- see header. Fails fast with a clear
# message rather than racing other array tasks' pulls.
MISSING=0
for m in "${MODELS[@]}" "$JUDGE_MODEL"; do
  if ! OLLAMA_HOST="127.0.0.1:${PORT}" ollama list | grep -qF "$m"; then
    echo "  MISSING: $m"
    MISSING=1
  fi
done
if [ "$MISSING" -eq 1 ]; then
  echo "ABORT: run cluster/slurm/pull_models.sh once and wait for it to finish first."
  kill "$SERVER_PID" 2>/dev/null || true
  exit 1
fi

cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT

TASK_ID="${SLURM_ARRAY_TASK_ID:-0}"
TOPICS=(violence sexual harmful unethical illegal)

if [ "$TASK_ID" -le 4 ]; then
  # ---- OR-Bench arm: one topic per array task -----------------------------
  TOPIC="${TOPICS[$TASK_ID]}"
  CSV="data/orbench_${TOPIC}200.csv"
  echo "=== Task $TASK_ID: topic=$TOPIC ==="

  echo "--- English: 4 prefixes, all 4 models (run.py's own default loop) ---"
  EN_FILES=()
  for prefix in none lawyer supreme-court jailbreak; do
    OUT="results/english/orbench_${TOPIC}200_${prefix}.csv"
    python3 run.py --prompts-file "$CSV" --languages en --prefix "$prefix" \
      --ollama-url "$URL" \
      --incremental-output "results/english/orbench_${TOPIC}200_${prefix}_incremental.csv" \
      --output "$OUT"
    EN_FILES+=("$OUT")
    JUDGE_OUT="results/judge/${TOPIC}_en_${prefix}.csv"
    python3 run_judge.py --in "$OUT" --prompts-file "$CSV" --request full \
      --judge "$JUDGE_MODEL" --ollama-url "$URL" --out "$JUDGE_OUT"
  done
  python3 "$CONCAT" "results/english/orbench_${TOPIC}200_all.csv" \
    "${EN_FILES[@]}" --add-condition

  echo "--- French/German: 2 prefixes, all 4 models ---"
  FRDE_FILES=()
  for prefix in none supreme-court; do
    OUT="results/french_german/orbench_${TOPIC}200_${prefix}_frde.csv"
    python3 run.py --prompts-file "$CSV" --languages fr de --prefix "$prefix" \
      --ollama-url "$URL" \
      --incremental-output "results/french_german/orbench_${TOPIC}200_${prefix}_frde_incremental.csv" \
      --output "$OUT"
    FRDE_FILES+=("$OUT")
    JUDGE_OUT="results/judge/${TOPIC}_frde_${prefix}.csv"
    python3 run_judge.py --in "$OUT" --prompts-file "$CSV" --request full \
      --judge "$JUDGE_MODEL" --ollama-url "$URL" --out "$JUDGE_OUT"
  done
  python3 "$CONCAT" "results/french_german/orbench_${TOPIC}200_frde_all.csv" \
    "${FRDE_FILES[@]}"

elif [ "$TASK_ID" -eq 5 ]; then
  # ---- Real BGer paragraphs: one output file per model ---------------------
  echo "=== Task 5: real BGer paragraphs, task-mode all ==="
  CSV="data/bger_para200.csv"
  for m in "${MODELS[@]}"; do
    short="${SHORT_NAME[$m]}"
    OUT="results/real_text/bger_para/${short}.csv"
    python3 run.py --prompts-file "$CSV" --languages en fr de --task-mode all \
      --ollama-models "$m" --ollama-url "$URL" \
      --incremental-output "results/real_text/bger_para/${short}_incremental.csv" \
      --output "$OUT"
    python3 run_judge.py --in "$OUT" --prompts-file "$CSV" --request full \
      --judge "$JUDGE_MODEL" --ollama-url "$URL" \
      --out "results/judge/bger_para/${short}.csv"
  done

else
  echo "ABORT: unexpected SLURM_ARRAY_TASK_ID=$TASK_ID (expected 0-5)."
  exit 1
fi

echo "TASK $TASK_ID DONE."
