#!/usr/bin/env bash
# Full sweep: every OR-Bench category x every condition (no task + each task),
# on all local Ollama models, for the chosen languages.
#
# Prerequisites (local Ollama):
#   ollama serve &
#   ollama pull llama3.1:8b
#   ollama pull qwen3:8b
#   ollama pull gemma4:e4b
#   ollama pull hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M
#
# Usage:
#   bash run_all.sh                 # English (paper main table)
#   LANGS="fr de" bash run_all.sh   # French + German
set -euo pipefail

LANGS="${LANGS:-en}"
CATEGORIES=(harmful illegal sexual unethical violence)
TASKS=(none lawyer judge jailbreak)   # 'none' = baseline, no prefix

for cat in "${CATEGORIES[@]}"; do
  for task in "${TASKS[@]}"; do
    echo "==================== ${cat} / ${task} ===================="
    python run.py \
      --data "data/orbench_${cat}.csv" \
      --task "${task}" \
      --languages ${LANGS} \
      --output "results/orbench_${cat}_${task}.csv"
  done
done

echo "All done. Results in results/orbench_<category>_<task>.csv"
