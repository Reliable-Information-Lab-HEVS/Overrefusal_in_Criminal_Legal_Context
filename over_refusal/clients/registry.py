"""Model & judge registry: reads ``models.yaml`` and builds backend clients.

This is the single place where "which models do we test" and "which judges
vote" are resolved. Both come from ``models.yaml`` at the project root, so the
Federal Tribunal can add a model or change the judge ensemble by editing one
YAML file -- no Python edits.

Backend types:
  * ``ollama``             -> OllamaClient (local server, no key)
  * ``openai_compatible``  -> OpenAICompatibleClient (any OpenAI-style HTTP API)
  * ``anthropic``          -> ClaudeClient   (judge backend; bespoke wire format)
  * ``gemini``             -> GeminiClient   (judge backend; bespoke wire format)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from over_refusal.config import DEFAULT_OLLAMA_TIMEOUT, OLLAMA_URL, PROJECT_ROOT

from .base import BaseClient
from .claude import ClaudeClient
from .gemini import GeminiClient
from .ollama import OllamaClient
from .openai_compatible import OpenAICompatibleClient

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment guard
    raise ImportError(
        "PyYAML is required to read models.yaml / roles.yaml. "
        "Install it with:  pip install pyyaml   (or: pip install -r requirements.txt)"
    ) from exc


DEFAULT_MODELS_FILE = PROJECT_ROOT / "models.yaml"

# Backend type labels (also written verbatim to the CSV "backend" column).
OLLAMA = "ollama"
OPENAI_COMPATIBLE = "openai_compatible"
ANTHROPIC = "anthropic"
GEMINI = "gemini"


@dataclass
class ModelSpec:
    """A model under test: what to call it, how to reach it, and its client."""
    name: str          # CSV "model" value + model id sent to the API
    backend: str       # CSV "backend" value (the backend type label)
    client: BaseClient


@dataclass
class JudgeSpec:
    """One member of the LLM-as-judge ensemble."""
    name: str          # short judge id (e.g. "gpt", "claude", "gemini")
    model: str         # model id passed to the client
    client: BaseClient


def _read_yaml(path: Optional[str]) -> dict:
    path = Path(path) if path else DEFAULT_MODELS_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Model config not found: {path}\n"
            f"Create it (see the documented example committed at "
            f"{DEFAULT_MODELS_FILE.name})."
        )
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


def build_client(entry: Dict) -> BaseClient:
    """Instantiate the right client for one models.yaml entry."""
    backend = entry.get("backend")

    if backend == OLLAMA:
        return OllamaClient(
            base_url=entry.get("base_url", OLLAMA_URL),
            timeout=entry.get("timeout", DEFAULT_OLLAMA_TIMEOUT),
        )

    if backend == OPENAI_COMPATIBLE:
        if not entry.get("base_url"):
            raise ValueError(
                f"openai_compatible entry '{entry.get('name')}' needs a base_url"
            )
        return OpenAICompatibleClient(
            base_url=entry["base_url"],
            api_key_env=entry.get("api_key_env"),
            headers=entry.get("headers"),
            timeout=entry.get("timeout", 90),
            retry=entry.get("retry"),
        )

    # Bespoke judge backends (kept verbatim to preserve OR-Bench methodology).
    # They read their own key from the environment (ANTHROPIC_API_KEY /
    # GEMINI_API_KEY), so api_key_env in the YAML is documentation only.
    if backend == ANTHROPIC:
        return ClaudeClient()
    if backend == GEMINI:
        return GeminiClient()

    raise ValueError(
        f"Unknown backend '{backend}' in model config. Supported: "
        f"{OLLAMA}, {OPENAI_COMPATIBLE}, {ANTHROPIC}, {GEMINI}"
    )


def resolve_models(
    models_file: Optional[str] = None,
    ollama_only: bool = False,
    api_only: bool = False,
    ollama_models: Optional[List[str]] = None,
) -> List[ModelSpec]:
    """Build the ordered list of models to test from models.yaml.

    Selection flags filter the YAML list (they never bypass it):
      * ``ollama_models`` replaces the ollama-backed entries with the given names
        (used by ``--ollama-models``);
      * ``ollama_only`` keeps only ollama entries;
      * ``api_only`` keeps only non-ollama entries.

    Order is ollama models first, then the rest -- matching the historical
    build order so existing runs are reproduced row-for-row.
    """
    data = _read_yaml(models_file)
    entries = data.get("models", []) or []

    specs = [
        ModelSpec(name=e["name"], backend=e["backend"], client=build_client(e))
        for e in entries
    ]

    ollama_specs = [s for s in specs if s.backend == OLLAMA]
    api_specs = [s for s in specs if s.backend != OLLAMA]

    # --ollama-models overrides the ollama set entirely (names only).
    if ollama_models is not None:
        ollama_specs = [
            ModelSpec(name=n, backend=OLLAMA, client=OllamaClient())
            for n in ollama_models
        ]

    result: List[ModelSpec] = []
    if not api_only:
        result.extend(ollama_specs)
    if not ollama_only:
        result.extend(api_specs)
    return result


def load_judge_names(models_file: Optional[str] = None) -> List[str]:
    """Return the judge ids declared in models.yaml, in file order."""
    data = _read_yaml(models_file)
    return [j["name"] for j in (data.get("judges", []) or [])]


def resolve_judges(
    judge_names: Optional[List[str]] = None,
    models_file: Optional[str] = None,
) -> List[JudgeSpec]:
    """Build the judge ensemble from models.yaml.

    ``judge_names`` selects a subset (in the given order); None means all
    judges declared in the file.
    """
    data = _read_yaml(models_file)
    declared = {j["name"]: j for j in (data.get("judges", []) or [])}
    if not declared:
        raise ValueError("No judges declared in models.yaml (need a `judges:` list).")

    if judge_names is None:
        judge_names = list(declared.keys())

    out: List[JudgeSpec] = []
    for name in judge_names:
        if name not in declared:
            raise ValueError(
                f"Unknown judge '{name}'. Available: {list(declared)}"
            )
        entry = declared[name]
        out.append(JudgeSpec(name=name, model=entry["model"], client=build_client(entry)))
    return out
