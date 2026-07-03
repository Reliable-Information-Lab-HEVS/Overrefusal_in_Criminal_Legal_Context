"""Project configuration.

All secrets (API keys) are read from environment variables.
For local development, copy `.env.example` to `.env` and fill in your keys,
then export them before running. Never commit real keys to git.
"""

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
DEFAULT_OLLAMA_TIMEOUT = 120

# NOTE: the list of models to evaluate lives in the user-editable
# `models.yaml` at the project root (read via over_refusal.clients.registry).
# To add or change a model, edit that file -- no Python changes needed.


# -----------------------------------------------------------------------------
# Languages: Swiss official languages plus English for publication
# -----------------------------------------------------------------------------
SUPPORTED_LANGUAGES = ["fr", "de", "it", "en"]
DEFAULT_LANGUAGES = ["fr", "de", "it"]


# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default prompts CSV: the shipped example template (one documented row).
DEFAULT_PROMPTS_FILE = str(PROJECT_ROOT / "data" / "sample_TF.csv")

# Default folder where run results are written
DEFAULT_RESULTS_DIR = str(PROJECT_ROOT / "results")

# Static data files used by the refusal detector
PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data"
REFUSAL_KEYWORDS_FILE = str(PACKAGE_DATA_DIR / "refusal_keywords.json")
