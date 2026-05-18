"""Print a comprehensive over-refusal analysis report.

Reads one or more result CSV files (typically the API run and the Ollama run)
and prints a structured terminal report. Automatically detects whether the
files have been processed by the LLM judge (judge_label / judge_is_refusal
columns) and shows side-by-side keyword vs judge comparison when applicable.

Sections:

  1. Executive summary
  2. Refusal rate by model (with judge overlay if available)
  3. Normal vs hard task variant effect
  4. Refusal rate by category
  5. Refusal rate by language
  6. Gemini server-side blocks deep-dive
  7. Sexual category heatmap (model x language)
  8. Cloud APIs vs local Ollama
  9. Judge-only refusals — cases the keyword detector missed
 10. Indirect refusals — subtle hedging detected by the judge
 11. Suspected false positives (keyword detector limits)
 12. Technical errors
 13. Recommended next steps

Usage:
  python -m over_refusal.tools.report results/bgr_apis_v3.csv \
                                      results/bgr_ollama_v3.csv

  python -m over_refusal.tools.report results/bgr_apis_v3_judged.csv \
                                      results/bgr_ollama_v3_judged.csv

The script tags rows automatically: any model name containing a colon
(e.g. "llama3.1:8b") is treated as a local Ollama model; everything else
is treated as a cloud API.
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List


W = 78  # report width


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_local_model(model_name: str) -> bool:
    return ":" in model_name


def is_gemini_server_block(row: Dict[str, str]) -> bool:
    p = row.get("response_preview", "")
    return ("finishReason=" in p) or ("blockReason=" in p)


def has_judge(rows: List[Dict[str, str]]) -> bool:
    """Return True if the rows include LLM-judge classification columns."""
    if not rows:
        return False
    return "judge_label" in rows[0] and "judge_is_refusal" in rows[0]


def is_judge_refused(row: Dict[str, str]) -> bool:
    return row.get("judge_is_refusal") == "True"


def is_kw_refused(row: Dict[str, str]) -> bool:
    return row.get("is_refused") == "True"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def bar(pct: float, width: int = 20) -> str:
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


def section(title: str) -> None:
    print()
    print("═" * W)
    print(f"  {title}")
    print("═" * W)


def print_header(label: str, judge_active: bool) -> None:
    print()
    print("╔" + "═" * (W - 2) + "╗")
    print("║" + " " * (W - 2) + "║")
    print("║" + label.center(W - 2) + "║")
    sub = ("Keyword detector + LLM judge (3-class taxonomy)"
           if judge_active else "Keyword detector only — run the LLM judge for 3-class taxonomy")
    print("║" + sub.center(W - 2) + "║")
    print("║" + " " * (W - 2) + "║")
    print("╚" + "═" * (W - 2) + "╝")


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------
def report_summary(rows: List[Dict[str, str]], judge_active: bool) -> None:
    n_total = len(rows)
    n_kw_ref = sum(1 for r in rows if is_kw_refused(r))
    n_errors = sum(1 for r in rows if r.get("is_error") == "True")
    n_models = len(set(r["model"] for r in rows))
    n_apis = sum(1 for m in set(r["model"] for r in rows) if not is_local_model(m))
    n_locals = sum(1 for m in set(r["model"] for r in rows) if is_local_model(m))
    n_prompts = len(set(r["prompt_id"].split("__")[0] for r in rows))
    n_langs = len(set(r["lang"] for r in rows))
    n_vars = len(set(r.get("task_variant", "") for r in rows))

    section("1. EXECUTIVE SUMMARY")
    print(f"""
  Dataset      : {n_prompts} BGer rulings × {n_langs} languages × {n_vars} task variants
  Models       : {n_models} ({n_apis} API + {n_locals} local)
  Total runs   : {n_total}
  Errors       : {n_errors}  ({100*n_errors/n_total:.2f}%)""")

    if judge_active:
        labels = Counter(r["judge_label"] for r in rows)
        n_direct_ref = labels.get("direct_refusal", 0)
        n_indirect_ref = labels.get("indirect_refusal", 0)
        n_direct_ans = labels.get("direct_answer", 0)
        n_judge_ref = n_direct_ref + n_indirect_ref
        agreement_count = sum(
            1 for r in rows if is_kw_refused(r) == is_judge_refused(r)
        )
        agreement = 100 * agreement_count / n_total
        print(f"""
  Refusals (keyword) : {n_kw_ref:4} ({100*n_kw_ref/n_total:.1f}%)
  Refusals (judge)   : {n_judge_ref:4} ({100*n_judge_ref/n_total:.1f}%)
    └─ direct        : {n_direct_ref}
    └─ indirect      : {n_indirect_ref}
  Direct answers     : {n_direct_ans:4} ({100*n_direct_ans/n_total:.1f}%)
  Keyword vs judge agreement : {agreement:.1f}%""")
    else:
        print(f"""
  Refusals (keyword) : {n_kw_ref:4} ({100*n_kw_ref/n_total:.1f}%)""")


def report_by_model(rows: List[Dict[str, str]], judge_active: bool) -> None:
    by_model: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"kw": 0, "judge": 0, "direct_ref": 0, "indirect_ref": 0, "total": 0}
    )
    for r in rows:
        m = r["model"]
        by_model[m]["total"] += 1
        if is_kw_refused(r):
            by_model[m]["kw"] += 1
        if judge_active:
            if r.get("judge_label") == "direct_refusal":
                by_model[m]["direct_ref"] += 1
                by_model[m]["judge"] += 1
            elif r.get("judge_label") == "indirect_refusal":
                by_model[m]["indirect_ref"] += 1
                by_model[m]["judge"] += 1

    section("2. REFUSAL RATE BY MODEL")
    sorted_models = sorted(
        by_model.items(),
        key=lambda x: -(x[1]["judge"] if judge_active else x[1]["kw"]) / x[1]["total"],
    )

    if judge_active:
        print(f"\n  {'Model':<28} {'Backend':<14}  {'Keyword':>10}  {'Judge':>10}  Bar (judge)")
        print(f"  {'-'*28} {'-'*14}  {'-'*10}  {'-'*10}  {'-'*20}")
        for m, d in sorted_models:
            kw_rate = 100 * d["kw"] / d["total"]
            j_rate = 100 * d["judge"] / d["total"]
            backend = "Local (Ollama)" if is_local_model(m) else "API (cloud)"
            print(
                f"  {m:<28} {backend:<14}  {d['kw']:>2}/{d['total']:<3} ({kw_rate:4.1f}%)  "
                f"{d['judge']:>2}/{d['total']:<3} ({j_rate:4.1f}%)  {bar(j_rate)}"
            )
        print()
        print(f"  {'Model':<28}  {'Direct ref.':>11}  {'Indirect ref.':>13}  {'Direct ans.':>11}")
        print(f"  {'-'*28}  {'-'*11}  {'-'*13}  {'-'*11}")
        for m, d in sorted_models:
            direct_ans = d["total"] - d["judge"]
            print(
                f"  {m:<28}  {d['direct_ref']:>11}  {d['indirect_ref']:>13}  {direct_ans:>11}"
            )
    else:
        print(f"\n  {'Model':<28} {'Backend':<14}  {'Refused':>10}  {'Rate':>7}  Bar")
        print(f"  {'-'*28} {'-'*14}  {'-'*10}  {'-'*7}  {'-'*20}")
        for m, d in sorted_models:
            rate = 100 * d["kw"] / d["total"]
            backend = "Local (Ollama)" if is_local_model(m) else "API (cloud)"
            print(
                f"  {m:<28} {backend:<14}  {d['kw']:>3} / {d['total']:<4}  "
                f"{rate:>5.1f}%  {bar(rate)}"
            )


def report_normal_vs_hard(rows: List[Dict[str, str]], judge_active: bool) -> None:
    by_mv: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"kw": 0, "judge": 0, "total": 0})
    )
    for r in rows:
        m, v = r["model"], r["task_variant"]
        by_mv[m][v]["total"] += 1
        if is_kw_refused(r):
            by_mv[m][v]["kw"] += 1
        if judge_active and is_judge_refused(r):
            by_mv[m][v]["judge"] += 1

    metric = "judge" if judge_active else "kw"
    metric_label = "judge-validated" if judge_active else "keyword"

    section(f"3. NORMAL vs HARD — TASK VARIANT EFFECT ({metric_label})")
    print(
        f"\n  {'Model':<28}    {'Normal':>13}    {'Hard':>13}    "
        f"Delta    Effect"
    )
    print(f"  {'-'*28}    {'-'*13}    {'-'*13}    {'-'*7}  {'-'*8}")
    for m in sorted(by_mv.keys()):
        n = by_mv[m]["normal"]
        h = by_mv[m]["hard"]
        n_rate = 100 * n[metric] / n["total"] if n["total"] else 0
        h_rate = 100 * h[metric] / h["total"] if h["total"] else 0
        delta = h_rate - n_rate
        if delta > 0 and n[metric] > 0:
            effect = f"× {h[metric]/n[metric]:.1f}"
        elif delta > 0:
            effect = "new refusals"
        elif delta == 0:
            effect = "no effect"
        else:
            effect = "decrease"
        n_str = f"{n[metric]}/{n['total']} ({n_rate:.1f}%)"
        h_str = f"{h[metric]}/{h['total']} ({h_rate:.1f}%)"
        print(
            f"  {m:<28}    {n_str:>13}    {h_str:>13}    "
            f"{delta:+5.1f}%   {effect}"
        )

    n_norm_ref = sum(
        1 for r in rows
        if r["task_variant"] == "normal"
        and (is_judge_refused(r) if judge_active else is_kw_refused(r))
    )
    n_norm_tot = sum(1 for r in rows if r["task_variant"] == "normal")
    n_hard_ref = sum(
        1 for r in rows
        if r["task_variant"] == "hard"
        and (is_judge_refused(r) if judge_active else is_kw_refused(r))
    )
    n_hard_tot = sum(1 for r in rows if r["task_variant"] == "hard")
    delta_pp = (
        100 * n_hard_ref / n_hard_tot - 100 * n_norm_ref / n_norm_tot
        if n_hard_tot and n_norm_tot else 0
    )
    print(f"""
  ─ Aggregated across all models ──────────────────────────────────────────
   Normal task : {n_norm_ref:3}/{n_norm_tot} refused ({100*n_norm_ref/n_norm_tot:.1f}%)
   Hard task   : {n_hard_ref:3}/{n_hard_tot} refused ({100*n_hard_ref/n_hard_tot:.1f}%)
   Delta       : {delta_pp:+.1f} percentage points""")


def report_by_category(rows: List[Dict[str, str]], judge_active: bool) -> None:
    by_cat: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"kw": 0, "judge": 0, "total": 0}
    )
    for r in rows:
        c = r["category"]
        by_cat[c]["total"] += 1
        if is_kw_refused(r):
            by_cat[c]["kw"] += 1
        if judge_active and is_judge_refused(r):
            by_cat[c]["judge"] += 1

    metric = "judge" if judge_active else "kw"
    metric_label = "judge" if judge_active else "keyword"
    section(f"4. REFUSAL RATE BY OR-BENCH CATEGORY ({metric_label})")
    print(f"\n  {'Category':<18}  {'Refused':>10}  {'Rate':>7}  Bar")
    print(f"  {'-'*18}  {'-'*10}  {'-'*7}  {'-'*20}")
    for cat, d in sorted(
        by_cat.items(), key=lambda x: -x[1][metric] / x[1]["total"]
    ):
        rate = 100 * d[metric] / d["total"]
        print(
            f"  {cat:<18}  {d[metric]:>3} / {d['total']:<4}  {rate:>5.1f}%  {bar(rate)}"
        )


def report_by_language(rows: List[Dict[str, str]], judge_active: bool) -> None:
    by_lang: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"kw": 0, "judge": 0, "total": 0}
    )
    for r in rows:
        l = r["lang"]
        by_lang[l]["total"] += 1
        if is_kw_refused(r):
            by_lang[l]["kw"] += 1
        if judge_active and is_judge_refused(r):
            by_lang[l]["judge"] += 1

    metric = "judge" if judge_active else "kw"
    metric_label = "judge" if judge_active else "keyword"
    lang_names = {"fr": "French", "de": "German", "it": "Italian", "en": "English"}
    section(f"5. REFUSAL RATE BY LANGUAGE ({metric_label})")
    print(f"\n  {'Language':<14}  {'Refused':>10}  {'Rate':>7}  Bar")
    print(f"  {'-'*14}  {'-'*10}  {'-'*7}  {'-'*20}")
    for lang, d in sorted(
        by_lang.items(), key=lambda x: -x[1][metric] / x[1]["total"]
    ):
        rate = 100 * d[metric] / d["total"]
        print(
            f"  {lang_names.get(lang, lang):<14}  {d[metric]:>3} / {d['total']:<4}  "
            f"{rate:>5.1f}%  {bar(rate)}"
        )


def report_gemini_deep_dive(rows: List[Dict[str, str]], judge_active: bool) -> None:
    gemini = [r for r in rows if "gemini" in r["model"].lower()]
    if not gemini:
        return
    refused_kw = [r for r in gemini if is_kw_refused(r)]
    server = [r for r in refused_kw if is_gemini_server_block(r)]
    text_kw = [r for r in refused_kw if not is_gemini_server_block(r)]
    errors = [r for r in gemini if r.get("is_error") == "True"]

    section("6. GEMINI 2.5 FLASH — SERVER-SIDE BLOCKS DEEP DIVE")
    print(f"""
  Gemini total runs            : {len(gemini)}
  Gemini errors (true bugs)    : {len(errors)}

  KEYWORD CLASSIFICATION
  Refusals (keyword)           : {len(refused_kw)} ({100*len(refused_kw)/len(gemini):.1f}%)
    └─ via server-side filter  : {len(server)}
    └─ via textual refusal     : {len(text_kw)}""")

    if judge_active:
        judge_ref = [r for r in gemini if is_judge_refused(r)]
        judge_direct = [r for r in gemini if r.get("judge_label") == "direct_refusal"]
        judge_indirect = [r for r in gemini if r.get("judge_label") == "indirect_refusal"]
        # Cases the judge caught that keyword missed
        judge_only = [r for r in gemini
                      if not is_kw_refused(r) and is_judge_refused(r)]
        print(f"""
  JUDGE CLASSIFICATION
  Refusals (judge)             : {len(judge_ref)} ({100*len(judge_ref)/len(gemini):.1f}%)
    └─ direct_refusal          : {len(judge_direct)}
    └─ indirect_refusal        : {len(judge_indirect)}
  Cases keyword missed         : {len(judge_only)}""")

    prompt_blocks = sum(1 for r in server if "prompt blockReason" in r["response_preview"])
    finish_blocks = len(server) - prompt_blocks
    print(f"\n  Server-block typology:")
    print(
        f"    promptFeedback.blockReason  : {prompt_blocks:3} cases  "
        f"(input rejected pre-generation)"
    )
    print(
        f"    candidate.finishReason      : {finish_blocks:3} cases  "
        f"(generation aborted server-side)"
    )

    print(f"\n  Prompts that trigger Gemini server blocks (across all langs × variants):")
    triggers = Counter(r["prompt_id"].split("__")[0] for r in server)
    for pid, n in sorted(triggers.items(), key=lambda x: -x[1]):
        cat = next(r["category"] for r in server if r["prompt_id"].startswith(pid))
        cases = [r for r in gemini if r["prompt_id"].startswith(pid)]
        print(f"    {pid}  [{cat}]  blocked {n}/{len(cases)} cases")


def report_sexual_heatmap(rows: List[Dict[str, str]], judge_active: bool) -> None:
    sexual = [r for r in rows if r["category"] == "sexual"]
    if not sexual:
        return
    metric_label = "judge-validated" if judge_active else "keyword"
    section(f"7. SEXUAL CATEGORY HEATMAP — {metric_label}")
    print(f"\n  Total sexual-category runs: {len(sexual)}")

    heatmap: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"refused": 0, "total": 0})
    )
    for r in sexual:
        heatmap[r["model"]][r["lang"]]["total"] += 1
        refused = is_judge_refused(r) if judge_active else is_kw_refused(r)
        if refused:
            heatmap[r["model"]][r["lang"]]["refused"] += 1

    print(f"\n  {'Model':<28}    fr     de     it     en   Total")
    print(f"  {'-'*28}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*5}")
    for m in sorted(heatmap.keys()):
        line = f"  {m:<28}"
        total_ref, total_tot = 0, 0
        for lang in ["fr", "de", "it", "en"]:
            d = heatmap[m][lang]
            total_ref += d["refused"]
            total_tot += d["total"]
            line += "      ·" if d["refused"] == 0 else f"   {d['refused']}/{d['total']}"
        line += f"   {total_ref}/{total_tot}"
        print(line)


def report_api_vs_local(rows: List[Dict[str, str]], judge_active: bool) -> None:
    apis = [r for r in rows if not is_local_model(r["model"])]
    locals_ = [r for r in rows if is_local_model(r["model"])]
    if not apis or not locals_:
        return
    metric_fn = is_judge_refused if judge_active else is_kw_refused
    metric_label = "judge" if judge_active else "keyword"
    api_ref = sum(1 for r in apis if metric_fn(r))
    api_err = sum(1 for r in apis if r.get("is_error") == "True")
    loc_ref = sum(1 for r in locals_ if metric_fn(r))
    loc_err = sum(1 for r in locals_ if r.get("is_error") == "True")
    gemini = [r for r in apis if "gemini" in r["model"].lower()]
    gemini_ref = sum(1 for r in gemini if metric_fn(r))

    section(f"8. CLOUD APIs vs LOCAL OLLAMA ({metric_label})")
    print(f"""
  Cloud APIs    : {api_ref:3}/{len(apis)} refused ({100*api_ref/len(apis):.1f}%) ({api_err} errors)
  Local Ollama  : {loc_ref:3}/{len(locals_)} refused ({100*loc_ref/len(locals_):.1f}%) ({loc_err} errors)""")

    if gemini:
        no_gem = api_ref - gemini_ref
        no_gem_tot = len(apis) - len(gemini)
        if no_gem_tot:
            print(f"""
  ⚠️  Caveat: API refusal rate is dominated by Gemini's server filter.
     Excluding Gemini: APIs refuse {no_gem}/{no_gem_tot} = {100*no_gem/no_gem_tot:.1f}%""")


def report_judge_only_refusals(rows: List[Dict[str, str]]) -> None:
    """Cases the judge classified as refusal but the keyword missed."""
    missed = [r for r in rows if not is_kw_refused(r) and is_judge_refused(r)]
    section("9. JUDGE-ONLY REFUSALS — cases the keyword detector missed")
    print(f"""
  These {len(missed)} cases were classified as refused by the LLM judge but
  did NOT match any refusal keyword. They are the value-add of the judge:
  subtle hedging, partial responses, or refusals worded creatively enough
  to escape the keyword list.""")
    if missed:
        print(f"\n  {'Model':<25} {'Prompt':<18} {'Lang':<5} {'Judge label':<18} Preview")
        print(f"  {'-'*25} {'-'*18} {'-'*5} {'-'*18} {'-'*30}")
        for r in missed:
            print(
                f"  {r['model']:<25} {r['prompt_id']:<18} {r['lang']:<5} "
                f"{r['judge_label']:<18} {r['response_preview'][:50]}..."
            )


def report_indirect_refusals(rows: List[Dict[str, str]]) -> None:
    indirect = [r for r in rows if r.get("judge_label") == "indirect_refusal"]
    section("10. INDIRECT REFUSALS — subtle hedging detected by the judge")
    print(f"""
  These {len(indirect)} cases were classified as 'indirect_refusal': the model
  appeared to start answering but ultimately did not deliver the requested
  content (refusal embedded in a polite preamble, truncated note, etc.).
  This category is the main reason for using an LLM judge over keywords.""")
    if indirect:
        print(f"\n  {'Model':<25} {'Prompt':<18} {'Lang':<5} Preview")
        print(f"  {'-'*25} {'-'*18} {'-'*5} {'-'*40}")
        for r in indirect:
            print(
                f"  {r['model']:<25} {r['prompt_id']:<18} {r['lang']:<5} "
                f"{r['response_preview'][:50]}..."
            )


def report_false_positives(rows: List[Dict[str, str]], judge_active: bool) -> None:
    """Keyword said refused, but judge said direct_answer (or response looks like an answer)."""
    section("11. SUSPECTED FALSE POSITIVES OF THE KEYWORD DETECTOR")
    if judge_active:
        false_pos = [
            r for r in rows
            if is_kw_refused(r) and not is_judge_refused(r)
        ]
        print(f"""
  {len(false_pos)} cases were keyword-flagged as refused but classified as
  direct_answer by the LLM judge. These are confirmed false positives of
  the keyword detector — the judge read the full response and disagreed.""")
        if false_pos:
            print(f"\n  {'Model':<25} {'Prompt':<18} {'Lang':<5} Preview")
            print(f"  {'-'*25} {'-'*18} {'-'*5} {'-'*40}")
            for r in false_pos:
                print(
                    f"  {r['model']:<25} {r['prompt_id']:<18} {r['lang']:<5} "
                    f"{r['response_preview'][:50]}..."
                )
    else:
        # No judge: best-effort heuristic on prefix
        suspicious = []
        for r in rows:
            if not is_kw_refused(r):
                continue
            if is_gemini_server_block(r):
                continue
            preview = r["response_preview"]
            if preview.startswith(("**", "###", "INTERNAL", "1.", "Im ", "Nel ", "En ", "On ")):
                suspicious.append(r)
        print(f"""
  {len(suspicious)} cases where the keyword detector flagged a refusal but
  the response_preview begins with what looks like a real answer.
  Run the LLM judge on this CSV to confirm or refute these cases.""")
        if suspicious:
            print(f"\n  {'Model':<25} {'Prompt':<18} {'Lang':<5} Preview start")
            print(f"  {'-'*25} {'-'*18} {'-'*5} {'-'*40}")
            for r in suspicious:
                print(
                    f"  {r['model']:<25} {r['prompt_id']:<18} {r['lang']:<5} "
                    f"{r['response_preview'][:50]}..."
                )


def report_errors(rows: List[Dict[str, str]]) -> None:
    errors = [r for r in rows if r.get("is_error") == "True"]
    section("12. TECHNICAL ERRORS")
    print(f"\n  Total errors: {len(errors)} ({100*len(errors)/len(rows):.2f}%)")
    for r in errors:
        print(f"\n  • {r['model']} | {r['prompt_id']} | {r['lang']}")
        print(f"    {r['response_preview'][:120]}")


def report_next_steps(judge_active: bool) -> None:
    section("13. RECOMMENDED NEXT STEPS")
    if judge_active:
        print("""
  1. STORE FULL RESPONSES (currently 500-char preview only)
     Modify evaluation.py to add a response_full column.

  2. RETRY ANY OLLAMA TIMEOUTS
     Increase DEFAULT_OLLAMA_TIMEOUT and re-run the affected prompts.

  3. WRITE-UP — KEY FINDINGS TO INCLUDE IN THE THESIS
     • Gemini's server-side PROHIBITED_CONTENT filter on TF jurisprudence
     • Llama 3.1's normal-vs-hard amplification (judge-confirmed)
     • Claude / Qwen 2.5: 0% refusal — empirical contrast with OR-Bench's
       reputation that Claude is the most refusal-prone
     • Indirect refusals: the value-add of the LLM judge over keywords
""")
    else:
        print("""
  1. RUN THE LLM JUDGE on these CSVs to get the 3-class taxonomy:
     python -m over_refusal.judge --input <run.csv> --only-ambiguous

  2. STORE FULL RESPONSES (currently 500-char preview only)
     Modify evaluation.py to add a response_full column.

  3. RETRY ANY OLLAMA TIMEOUTS
     Increase DEFAULT_OLLAMA_TIMEOUT and re-run the affected prompts.
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_paths",
        nargs="+",
        help="One or more result CSV paths (raw or judged)",
    )
    parser.add_argument(
        "--label",
        default="OVER-REFUSAL BENCHMARK — SWISS FEDERAL COURT (BGer)",
        help="Header label for the report",
    )
    args = parser.parse_args()

    rows: List[Dict[str, str]] = []
    for p in args.csv_paths:
        path = Path(p)
        if not path.exists():
            sys.exit(f"File not found: {path}")
        rows.extend(load_csv(path))

    if not rows:
        sys.exit("No rows loaded.")

    judge_active = has_judge(rows)

    print_header(args.label, judge_active)
    report_summary(rows, judge_active)
    report_by_model(rows, judge_active)
    report_normal_vs_hard(rows, judge_active)
    report_by_category(rows, judge_active)
    report_by_language(rows, judge_active)
    report_gemini_deep_dive(rows, judge_active)
    report_sexual_heatmap(rows, judge_active)
    report_api_vs_local(rows, judge_active)
    if judge_active:
        report_judge_only_refusals(rows)
        report_indirect_refusals(rows)
    report_false_positives(rows, judge_active)
    report_errors(rows)
    report_next_steps(judge_active)
    print("═" * W)
    print()


if __name__ == "__main__":
    main()