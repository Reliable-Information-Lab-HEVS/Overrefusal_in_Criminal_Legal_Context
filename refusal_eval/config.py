"""Project configuration: paths, defaults, and API-key getters.

Secrets (PublicAI / DeepL keys) are read from environment variables only.
Copy `.env.example` to `.env` and fill it in; it is auto-loaded if
python-dotenv is installed.
"""

import os
from pathlib import Path


def _try_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)


# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = PROJECT_ROOT / "prompts"          # one JSON per task
RESULTS_DIR = PROJECT_ROOT / "results"

PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data"
REFUSAL_KEYWORDS_FILE = PACKAGE_DATA_DIR / "refusal_keywords.json"

_try_load_dotenv()


# -----------------------------------------------------------------------------
# Languages: the dataset and tasks are kept in French, German and English.
# -----------------------------------------------------------------------------
SUPPORTED_LANGUAGES = ["fr", "de", "en"]
DEFAULT_LANGUAGES = ["en"]


# -----------------------------------------------------------------------------
# Models — every model runs locally via Ollama (no remote API, no model keys).
# Apertus, llama, qwen, gemma, ... are all just Ollama tags here. Override with
# --ollama-models; pull them first with `ollama pull <tag>`.
# -----------------------------------------------------------------------------
DEFAULT_OLLAMA_MODELS = [
    "llama3.1:8b",
    "qwen3:8b",
    "gemma4:e4b",
    "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M",
]

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_TIMEOUT = 180

# Decoding temperature.
TEMPERATURE = 0.0


# -----------------------------------------------------------------------------
# API keys (env only) — DeepL is the only external service, used for translation.
# -----------------------------------------------------------------------------
def get_deepl_keys() -> str:
    """Comma-separated DeepL key(s); free keys end with ':fx'."""
    return os.environ.get("DEEPL_API_KEY", "")
