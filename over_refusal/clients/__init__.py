"""Backend clients and the model/judge registry.

Live backends:
  * OllamaClient            -- local Ollama server
  * OpenAICompatibleClient  -- any OpenAI /chat/completions endpoint
  * ClaudeClient            -- Anthropic Messages API (judge backend)
  * GeminiClient            -- Google Gemini API (judge backend)

The retired per-vendor clients live in ``clients/legacy/`` and are not imported
here. Which models/judges are actually used is resolved from ``models.yaml`` via
the registry helpers below.
"""

from .base import BaseClient
from .ollama import OllamaClient
from .openai_compatible import OpenAICompatibleClient
from .claude import ClaudeClient
from .gemini import GeminiClient
from .registry import (
    ModelSpec,
    JudgeSpec,
    build_client,
    resolve_models,
    resolve_judges,
    load_judge_names,
)

__all__ = [
    "BaseClient",
    "OllamaClient",
    "OpenAICompatibleClient",
    "ClaudeClient",
    "GeminiClient",
    "ModelSpec",
    "JudgeSpec",
    "build_client",
    "resolve_models",
    "resolve_judges",
    "load_judge_names",
]
