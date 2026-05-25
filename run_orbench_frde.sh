#!/usr/bin/env bash
# Run the over-refusal evaluation for the 5 OR-Bench categories,
# in French + German, with BOTH task variants:
#   - normal -> task_* columns (empty) => case text only        (SANS prefix)
#   - hard   -> task_hard_* columns    => legal-counsel prefix + text (AVEC prefix)
# (--task-mode all emits both variants in a single run.)
#
# Models (all local via Ollama): gemma4:e4b, qwen3:8b, Apertus-8B GGUF.
#
# Usage on the cluster:
#   ollama serve &                 # make sure the Ollama server is up
#   ollama pull gemma4:e4b
#   ollama pull qwen3:8b
#   ollama pull hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M
#   bash run_orbench_frde.sh
set -euo pipefail

MODELS=(gemma4:e4b qwen3:8b "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M")
CATEGORIES=(unethical violence)

for cat in "${CATEGORIES[@]}"; do
    echo "==================== ${cat} ===================="
    python run.py \
        --ollama-only \
        --ollama-models "${MODELS[@]}" \
        --languages fr de \
        --task-mode all \
        --prompts-file "data/orbench_${cat}200.csv" \
        --output "orbench_${cat}200_frde_results.csv"
done

echo "All categories done. Results in results/orbench_<cat>200_frde_results.csv"
