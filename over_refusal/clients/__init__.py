"""Backend clients and the model registry.

Live backends:
  * OllamaClient            -- local Ollama server
  * OpenAICompatibleClient  -- any OpenAI /chat/completions endpoint

Which models are actually used is resolved from ``models.yaml`` via the
registry helpers below.
"""

from .base import BaseClient
from .ollama import OllamaClient
from .openai_compatible import OpenAICompatibleClient
from .registry import (
    ModelSpec,
    build_client,
    resolve_models,
)

__all__ = [
    "BaseClient",
    "OllamaClient",
    "OpenAICompatibleClient",
    "ModelSpec",
    "build_client",
    "resolve_models",
]
