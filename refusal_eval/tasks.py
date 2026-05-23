"""Load task prefixes from the `prompts/` folder.

Each task lives in one JSON file `prompts/<name>.json`:

    {
      "task_en": "Summarize the main facts of this ruling in 3-5 sentences.",
      "task_fr": "Résumez les faits principaux de cet arrêt en 3-5 phrases.",
      "task_de": "Fassen Sie die wichtigsten Fakten dieses Urteils ... zusammen."
    }

A task is prepended to the case text to form the final prompt. The special
task name "none" means: send the case text alone, with no prefix.
"""

import json
from pathlib import Path
from typing import Dict, List

from refusal_eval.config import PROMPTS_DIR, SUPPORTED_LANGUAGES

NO_TASK = "none"


def available_tasks(prompts_dir: Path = PROMPTS_DIR) -> List[str]:
    """Names of the tasks defined in the prompts folder (without extension)."""
    return sorted(p.stem for p in Path(prompts_dir).glob("*.json"))


def load_task(name: str, prompts_dir: Path = PROMPTS_DIR) -> Dict[str, str]:
    """Return {lang: task_text} for the given task name.

    For NO_TASK, returns empty strings (no prefix in any language).
    """
    if name == NO_TASK:
        return {lang: "" for lang in SUPPORTED_LANGUAGES}

    path = Path(prompts_dir) / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Task '{name}' not found at {path}. "
            f"Available: {available_tasks(prompts_dir) + [NO_TASK]}"
        )
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {lang: (data.get(f"task_{lang}") or "").strip() for lang in SUPPORTED_LANGUAGES}


def build_prompt(task_text: str, case_text: str) -> str:
    """Glue a task prefix and the case text into the final prompt string."""
    task_text = (task_text or "").strip()
    case_text = (case_text or "").strip()
    if not task_text:
        return case_text
    if not case_text:
        return task_text
    return f"{task_text} {case_text}"
