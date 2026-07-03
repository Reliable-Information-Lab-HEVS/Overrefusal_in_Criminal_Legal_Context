"""Build refusal-rate summary tables from a list of result dicts.

The summary is printed to the terminal and, when a path is given, also written
to a text file next to the results CSV so it survives the terminal session.
"""

from typing import Dict, List, Optional


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

    def _format_table(self, title: str, stats: Dict[str, Dict[str, int]],
                      label: str, width: int) -> List[str]:
        lines = ["", "=" * 60, f"  {title}", "=" * 60]
        lines.append(f"{label:<{width}} {'Refused':>8} {'Total':>8} {'Rate':>8}")
        lines.append("-" * (width + 26))
        for key, values in sorted(stats.items()):
            total = values["total"]
            refused = values["refused"]
            rate = (refused / total * 100) if total > 0 else 0
            lines.append(f"{key:<{width}} {refused:>8} {total:>8} {rate:>7.1f}%")
        return lines

    def build_summary(self, results: List[Dict]) -> str:
        """Return the full summary (all tables) as one printable string."""
        lines: List[str] = []

        # By model
        lines += self._format_table("REFUSAL RATE BY MODEL",
                                    self._compute_stats(results, "model"),
                                    "Model", 25)

        # By language
        lines += self._format_table("REFUSAL RATE BY LANGUAGE",
                                    self._compute_stats(results, "lang"),
                                    "Language", 25)

        # By task variant if present
        if any("task_variant" in r for r in results):
            lines += self._format_table("REFUSAL RATE BY TASK VARIANT",
                                        self._compute_stats(results, "task_variant"),
                                        "Task variant", 25)

        # Cross-cut: model x language
        cross: Dict[str, Dict[str, int]] = {}
        for r in results:
            if r["is_error"]:
                continue
            key = f"{r['model']} | {r['lang']}"
            if key not in cross:
                cross[key] = {"total": 0, "refused": 0}
            cross[key]["total"] += 1
            if r["is_refused"]:
                cross[key]["refused"] += 1

        lines += self._format_table("REFUSAL RATE BY MODEL x LANGUAGE",
                                    cross, "Model | Language", 40)
        return "\n".join(lines)

    def print_summary(self, results: List[Dict],
                      summary_file: Optional[str] = None) -> None:
        """Print the summary; if `summary_file` is given, also write it there."""
        summary = self.build_summary(results)
        print(summary)
        if summary_file:
            with open(summary_file, "w", encoding="utf-8") as fh:
                fh.write(summary + "\n")
            print(f"\nSummary table written to: {summary_file}")
