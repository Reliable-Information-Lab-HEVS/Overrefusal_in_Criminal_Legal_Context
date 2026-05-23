"""Print refusal-rate summary tables from a list of result dicts."""

from typing import Dict, List


def _stats(results: List[Dict], field: str) -> Dict[str, Dict[str, int]]:
    """Group by `field`, count total / refused (errors excluded)."""
    out: Dict[str, Dict[str, int]] = {}
    for r in results:
        if r["is_error"]:
            continue
        key = r[field]
        out.setdefault(key, {"total": 0, "refused": 0})
        out[key]["total"] += 1
        if r["is_refused"]:
            out[key]["refused"] += 1
    return out


def _print_table(title: str, stats: Dict[str, Dict[str, int]], label: str, width: int) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print(f"{label:<{width}} {'Refused':>8} {'Total':>8} {'Rate':>8}")
    print("-" * (width + 26))
    for key, v in sorted(stats.items()):
        rate = (v["refused"] / v["total"] * 100) if v["total"] else 0
        print(f"{key:<{width}} {v['refused']:>8} {v['total']:>8} {rate:>7.1f}%")


def print_summary(results: List[Dict]) -> None:
    _print_table("REFUSAL RATE BY MODEL", _stats(results, "model"), "Model", 28)
    _print_table("REFUSAL RATE BY CATEGORY", _stats(results, "or_category"), "Category", 28)
    _print_table("REFUSAL RATE BY LANGUAGE", _stats(results, "lang"), "Language", 28)

    cross: Dict[str, Dict[str, int]] = {}
    for r in results:
        if r["is_error"]:
            continue
        key = f"{r['model']} | {r['or_category']}"
        cross.setdefault(key, {"total": 0, "refused": 0})
        cross[key]["total"] += 1
        if r["is_refused"]:
            cross[key]["refused"] += 1
    _print_table("REFUSAL RATE BY MODEL x CATEGORY", cross, "Model | Category", 40)
