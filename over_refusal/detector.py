"""Keyword-based refusal detector.

Loads refusal keywords from `data/refusal_keywords.json`.
This is the fast first-pass check from OR-Bench (Cui et al., 2025).
For ambiguous or partial refusals, the LLM-as-judge in `judge.py` is used.
"""

import json
from pathlib import Path
from typing import Dict, List

from over_refusal.config import REFUSAL_KEYWORDS_FILE


def _load_keywords(path: str) -> Dict[str, List[str]]:
    """Load the keyword JSON file. Drop the metadata "_comment" entry."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {lang: words for lang, words in data.items() if not lang.startswith("_")}


# Module-level cache: load once at import time
REFUSAL_KEYWORDS: Dict[str, List[str]] = _load_keywords(REFUSAL_KEYWORDS_FILE)


class RefusalDetector:
    """Detect a refusal by checking for known refusal phrases in the response."""

    def __init__(self, keywords: Dict[str, List[str]] = None):
        # Allow injecting a custom keyword dict for testing
        self.keywords = keywords if keywords is not None else REFUSAL_KEYWORDS

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase and unify apostrophe variants so curly/straight match."""
        text = text.lower().strip()
        # Replace curly/typographic apostrophes with the straight ASCII one
        for ch in ("\u2019", "\u02bc", "\u2018", "\u0060", "\u00b4"):
            text = text.replace(ch, "'")
        return text

    def is_refusal(self, response_text: str, lang: str = "en") -> bool:
        """Return True if the response contains a refusal phrase.

        Always also checks English keywords as a fallback, since a model can
        answer in English even when the prompt was in FR/DE/IT.
        """
        if not response_text:
            return False

        text_lower = self._normalize(response_text)
        lang_keywords = self.keywords.get(lang, [])
        english_keywords = self.keywords.get("en", [])
        all_keywords = lang_keywords + english_keywords

        for keyword in all_keywords:
            if keyword in text_lower:
                return True
        return False
