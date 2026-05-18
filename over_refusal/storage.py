"""Save evaluation results to a CSV file."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from over_refusal.config import DEFAULT_RESULTS_DIR


class ResultSaver:
    def save_csv(self, results: List[Dict], filename: str = None) -> str:
        """Write results to CSV. If filename is None, build a timestamped path
        under the default results/ folder.
        """
        if not results:
            raise ValueError("No results to save")

        if filename is None:
            Path(DEFAULT_RESULTS_DIR).mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = str(
                Path(DEFAULT_RESULTS_DIR) / f"over_refusal_results_{timestamp}.csv"
            )

        out_path = Path(filename)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

        print(f"\nResults saved to: {out_path}")
        return str(out_path)
