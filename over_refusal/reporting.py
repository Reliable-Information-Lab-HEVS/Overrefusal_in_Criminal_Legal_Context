"""Print refusal-rate summary tables from a list of result dicts."""

from typing import Dict, List


class SummaryPrinter:
    def _compute_stats(self, results: List[Dict], field_name: str) -> Dict[str, Dict[str, int]]:
        """Group results by `field_name` and count total / refused (errors excluded)."""
        stats: Dict[str, Dict[str, int]] = {}
        for r in results:
            if r["is_error"]:
                continue
            key = r[field_name]
            if key not in stats:
                stats[key] = {"total": 0, "refused": 0}
            stats[key]["total"] += 1
            if r["is_refused"]:
                stats[key]["refused"] += 1
        return stats

    def _print_table(self, title: str, stats: Dict[str, Dict[str, int]],
                     label: str, width: int) -> None:
        print("\n" + "=" * 60)
        print(f"  {title}")
        print("=" * 60)
        print(f"{label:<{width}} {'Refused':>8} {'Total':>8} {'Rate':>8}")
        print("-" * (width + 26))
        for key, values in sorted(stats.items()):
            total = values["total"]
            refused = values["refused"]
            rate = (refused / total * 100) if total > 0 else 0
            print(f"{key:<{width}} {refused:>8} {total:>8} {rate:>7.1f}%")

    def print_summary(self, results: List[Dict]) -> None:
        # By model
        self._print_table("REFUSAL RATE BY MODEL",
                          self._compute_stats(results, "model"),
                          "Model", 25)

        # By language
        self._print_table("REFUSAL RATE BY LANGUAGE",
                          self._compute_stats(results, "lang"),
                          "Language", 25)

        # By domain
        self._print_table("REFUSAL RATE BY DOMAIN",
                          self._compute_stats(results, "domain"),
                          "Domain", 25)

        # By task variant if present
        if any("task_variant" in r for r in results):
            self._print_table("REFUSAL RATE BY TASK VARIANT",
                              self._compute_stats(results, "task_variant"),
                              "Task variant", 25)

        # Cross-cut: model x domain
        cross: Dict[str, Dict[str, int]] = {}
        for r in results:
            if r["is_error"]:
                continue
            key = f"{r['model']} | {r['domain']}"
            if key not in cross:
                cross[key] = {"total": 0, "refused": 0}
            cross[key]["total"] += 1
            if r["is_refused"]:
                cross[key]["refused"] += 1

        self._print_table("REFUSAL RATE BY MODEL x DOMAIN",
                          cross, "Model | Domain", 40)
