"""Project configuration.

All secrets (API keys) are read from environment variables.
For local development, copy `.env.example` to `.env` and fill in your keys,
then export them before running. Never commit real keys to git.
"""

import os
from pathlib import Path


# -----------------------------------------------------------------------------
# Optional: auto-load a local `.env` file if python-dotenv is installed.
# This keeps the codebase working even if dotenv is not available.
# -----------------------------------------------------------------------------
def _try_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)


_try_load_dotenv()


# -----------------------------------------------------------------------------
# Local Ollama server (no key needed)
# -----------------------------------------------------------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_TIMEOUT = 1200
DEFAULT_OLLAMA_MODELS = ["llama3.1:8b", "qwen2.5:7b", "gemma3:4b"]


# -----------------------------------------------------------------------------
# Default model names per backend
# -----------------------------------------------------------------------------
MISTRAL_DEFAULT_MODEL = "mistral-small-latest"
OPENAI_DEFAULT_MODEL = "gpt-4.1"
CLAUDE_DEFAULT_MODEL = "claude-sonnet-4-20250514"
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"
APERTUS_DEFAULT_MODEL = "swiss-ai/apertus-8b-instruct"

# -----------------------------------------------------------------------------
# Languages: Swiss official languages plus English for publication
# -----------------------------------------------------------------------------
SUPPORTED_LANGUAGES = ["fr", "de", "it", "en"]
DEFAULT_LANGUAGES = ["fr", "de", "it"]


# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default prompts CSV (BGer cases with task + text in 4 languages)
DEFAULT_PROMPTS_FILE = str(PROJECT_ROOT / "data" / "bger_sample_0421_translated.csv")

# Default folder where run results are written
DEFAULT_RESULTS_DIR = str(PROJECT_ROOT / "results")

# Static data files used by detector and judge
PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data"
REFUSAL_KEYWORDS_FILE = str(PACKAGE_DATA_DIR / "refusal_keywords.json")
JUDGE_PROMPT_FILE = str(PACKAGE_DATA_DIR / "judge_prompt.txt")


# -----------------------------------------------------------------------------
# API key getters — env only, no fallback to hardcoded values
# -----------------------------------------------------------------------------
def get_mistral_key() -> str:
    return os.environ.get("MISTRAL_API_KEY", "")


def get_openai_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "")


def get_anthropic_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def get_gemini_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "")


def get_publicai_key():
    return os.getenv("PUBLICAI_API_KEY", "")
