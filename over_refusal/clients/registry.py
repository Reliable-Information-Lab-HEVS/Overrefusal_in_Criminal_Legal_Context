"""Model registry: reads ``models.yaml`` and builds backend clients.

This is the single place where "which models do we test" is resolved. The list
comes from ``models.yaml`` at the project root, so the Federal Tribunal can add
a model by editing one YAML file -- no Python edits.

Backend types:
  * ``ollama``             -> OllamaClient (local server, no key)
  * ``openai_compatible``  -> OpenAICompatibleClient (any OpenAI-style HTTP API)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from over_refusal.config import DEFAULT_OLLAMA_TIMEOUT, OLLAMA_URL, PROJECT_ROOT

from .base import BaseClient
from .ollama import OllamaClient
from .openai_compatible import OpenAICompatibleClient

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment guard
    raise ImportError(
        "PyYAML is required to read models.yaml. "
        "Install it with:  pip install pyyaml   (or: pip install -r requirements.txt)"
    ) from exc


DEFAULT_MODELS_FILE = PROJECT_ROOT / "models.yaml"

# Backend type labels (also written verbatim to the CSV "backend" column).
OLLAMA = "ollama"
OPENAI_COMPATIBLE = "openai_compatible"


@dataclass
class ModelSpec:
    """A model under test: what to call it, how to reach it, and its client."""
    name: str          # CSV "model" value + model id sent to the API
    backend: str       # CSV "backend" value (the backend type label)
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

    raise ValueError(
        f"Unknown backend '{backend}' in model config. Supported: "
        f"{OLLAMA}, {OPENAI_COMPATIBLE}"
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
