"""Project configuration.

The pipeline is on-premises only: all models run locally via Ollama, so there
are no API keys or remote endpoints to configure.
"""

from pathlib import Path


# -----------------------------------------------------------------------------
# Local Ollama server (no key needed)
# -----------------------------------------------------------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
# 300s (was 120s): headroom for long documents (swiss_defense_summarization)
# and for a shared, possibly GPU-contended Ollama server.
DEFAULT_OLLAMA_TIMEOUT = 300
# The four on-premises models from the paper. Override with --ollama-models.
DEFAULT_OLLAMA_MODELS = [
    "llama3.1:8b",
    "qwen3:8b",
    "gemma4:e4b",
    "hf.co/bartowski/swiss-ai_Apertus-8B-Instruct-2509-GGUF:Q4_K_M",
]


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
DEFAULT_PROMPTS_FILE = str(PROJECT_ROOT / "data" / "bger_sample.csv")

# Default folder where run results are written
DEFAULT_RESULTS_DIR = str(PROJECT_ROOT / "results")

# Static data file used by the keyword refusal detector
PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data"
REFUSAL_KEYWORDS_FILE = str(PACKAGE_DATA_DIR / "refusal_keywords.json")
