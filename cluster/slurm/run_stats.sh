#!/bin/bash
# CPU-only stats job: keyword-refusal aggregation, McNemar/Holm-Bonferroni,
# and the paper's tables/figures. No --gres requested at all -- none of this
# needs a GPU, so it queues on the CPU partition/qos and doesn't burn A100
# time on arithmetic.
#
# Run this AFTER run_experiments.sh's whole array (all 6 tasks) has
# completed -- it reads results/ files that array writes.
#
#SBATCH --job-name=overrefusal_stats
#SBATCH --output=cluster/slurm/logs/stats_%j.out
#SBATCH --error=cluster/slurm/logs/stats_%j.err
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --qos=normal

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
SCRIPT_PATH="$REPO_ROOT/cluster/slurm/run_stats.sh"
mkdir -p cluster/slurm/logs

SIF="${OVERREFUSAL_SIF:-$HOME/containers/overrefusal.sif}"

# Same re-exec-into-container pattern as run_experiments.sh, minus --nv --
# nothing here touches the GPU, only the pinned numpy/scipy/matplotlib venv.
if [ -z "${INSIDE_APPTAINER_OVERREFUSAL:-}" ]; then
  export INSIDE_APPTAINER_OVERREFUSAL=1
  exec apptainer exec --bind "$HOME:$HOME" --pwd "$REPO_ROOT" \
    "$SIF" bash "$SCRIPT_PATH" "$@"
fi

echo "=== 1. Rebuild judge_master_long.csv from this run's judge CSVs ==="
# results/english/mcnemar_analysis.py and results/french_german/
# mcnemar_analysis.py both hard-depend on this file (see
# cluster/slurm/build_judge_master_long.py's docstring for the reverse-
# engineered format). It aggregates every English + FR/DE judge CSV written
# by run_experiments.sh across all 5 OR-Bench topics.
JUDGE_INPUTS=(results/judge/*_en_*.csv results/judge/*_frde_*.csv)
mkdir -p "results/LLM-as-a-judge-final-aggregated-results"
python3 cluster/slurm/build_judge_master_long.py \
  "results/LLM-as-a-judge-final-aggregated-results/judge_master_long.csv" \
  "${JUDGE_INPUTS[@]}"

echo "=== 2. Unify OR-Bench result CSVs -> results/master_long.csv ==="
python3 helpers/unify.py

echo "=== 3. McNemar + Holm-Bonferroni, per arm (scripts already in results/) ==="
for dir in results/english results/french_german results/real_text; do
  if [ -f "$dir/mcnemar_analysis.py" ]; then
    echo "--- $dir/mcnemar_analysis.py ---"
    python3 "$dir/mcnemar_analysis.py"
  fi
  if [ -f "$dir/holm_bonferroni.py" ]; then
    echo "--- $dir/holm_bonferroni.py ---"
    python3 "$dir/holm_bonferroni.py"
  fi
done

echo "=== 4. Keyword-vs-judge agreement, keyword+judge combined verdict ==="
python3 helpers/judge_agreement.py
if [ -f helpers/final_refusal.py ]; then
  python3 helpers/final_refusal.py results/judge/bger_para/*.csv \
    --output results/real_text/final_refusal_summary.txt || true
fi

echo "=== 5. Figures and tables ==="
python3 helpers/heatmap.py
python3 helpers/table_frde.py
if [ -f helpers/table_realtext.py ]; then
  python3 helpers/table_realtext.py
fi

echo "STATS DONE. See results/master_long.csv, results/*/mcnemar_*.csv,"
echo "results/*/mcnemar_appendix.csv (where present), and the regenerated figures."
