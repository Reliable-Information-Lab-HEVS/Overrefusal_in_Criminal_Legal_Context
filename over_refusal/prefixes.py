"""Authority/role prefixes injected at run time (the "adapter" layer).

The prefix wordings live in ``roles.yaml`` at the project root (same convention
as ``models.yaml``). This module loads that file once at import and exposes:

  - ``PREFIXES``        condition -> language code -> wording
  - ``PREFIX_CHOICES``  ["none", "lawyer", "supreme-court", ...]
  - ``apply_prefix(prompt_text, condition, lang)``

The prefix is prepended VERBATIM to the prompt in the matching language: no
separator is inserted, the trailing space carried by each wording is the
separator (this reproduces the original paper runs, where the final prompt was
"<prefix ending in ': '><OR-Bench prompt>"). ``"none"`` is the implicit
no-prefix baseline and is NOT listed in roles.yaml.
"""

from pathlib import Path
from typing import Dict

from over_refusal.config import PROJECT_ROOT

try:
    import yaml  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "PyYAML is required to read roles.yaml. "
        "Install it with:  pip install pyyaml   (or: pip install -r requirements.txt)"
    ) from exc


ROLES_FILE = PROJECT_ROOT / "roles.yaml"

# The "no prefix" baseline. Exposed as a name so the CLI choices are uniform.
NONE = "none"

# The conditions this experiment ships, in canonical order. roles.yaml must
# declare exactly these (no more, no fewer): a typo or a dropped entry then
# fails loudly at import instead of silently changing the experiment.
EXPECTED_CONDITIONS = (
    "lawyer",
    "supreme-court",
    "lawyer-p1",
    "supreme-court-p1",
    "neutral",
    "lawyer-p2",
    "supreme-court-p2",
)


def _load_roles(path: Path = ROLES_FILE) -> Dict[str, Dict[str, str]]:
    """Read roles.yaml and validate the set of conditions at load time."""
    if not path.exists():
        raise FileNotFoundError(
            f"Roles file not found: {path}. It must declare the prefix conditions "
            f"{list(EXPECTED_CONDITIONS)} (one entry each, with per-language wordings)."
        )
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a mapping of conditions, got {type(data).__name__}")

    loaded = set(data)
    expected = set(EXPECTED_CONDITIONS)
    if loaded != expected:
        missing = expected - loaded
        extra = loaded - expected
        raise ValueError(
            f"{path.name} conditions {sorted(loaded)} do not match the expected "
            f"{sorted(expected)}"
            + (f"; missing: {sorted(missing)}" if missing else "")
            + (f"; unexpected: {sorted(extra)}" if extra else "")
        )

    # Rebuild in canonical order so PREFIX_CHOICES order is deterministic.
    return {cond: data[cond] for cond in EXPECTED_CONDITIONS}


# Loaded once at import, like detector.py caches its keyword lists.
PREFIXES: Dict[str, Dict[str, str]] = _load_roles()

# All valid --prefix choices, baseline first, then the canonical conditions.
PREFIX_CHOICES = [NONE] + list(EXPECTED_CONDITIONS)


def apply_prefix(prompt_text: str, condition: str, lang: str) -> str:
    """Prepend the prefix for ``condition`` in ``lang`` to ``prompt_text``.

    ``condition == "none"`` (or empty) returns the prompt unchanged. Raises
    ValueError if ``condition`` is unknown, or if it has no wording for ``lang``:
    we fail loudly rather than silently injecting another language's prefix,
    since language is an independent variable of the benchmark.
    """
    if not condition or condition == NONE:
        return prompt_text

    if condition not in PREFIXES:
        raise ValueError(
            f"Unknown prefix '{condition}'. Choices: {PREFIX_CHOICES}"
        )

    lang_map = PREFIXES[condition]
    if lang not in lang_map:
        raise ValueError(
            f"No '{condition}' prefix for language '{lang}'. "
            f"Available: {sorted(lang_map)}"
        )
    prefix = lang_map[lang]
    return f"{prefix}{prompt_text}"
