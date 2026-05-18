"""Apertus client (Swiss AI Initiative — EPFL/ETH Zurich/CSCS).

Routes through the Public AI Inference Utility (https://api.publicai.co/v1),
which is OpenAI-compatible. Authentication is a Public AI API key generated
at https://platform.publicai.co/settings/api-keys.

Available model IDs:
    - swiss-ai/apertus-8b-instruct
    - swiss-ai/apertus-70b-instruct

Public AI requires a User-Agent header on every request. Rate limit during
Swiss AI Weeks: 20 requests per minute.

The Public AI gateway can return transient 5xx errors (504 Gateway Timeout
in particular) when the backend GPU cluster is loaded or the prompt is
long. We retry such cases with exponential backoff before giving up.
"""
import time

import requests

from over_refusal.config import get_publicai_key
from .base import BaseClient


APERTUS_DEFAULT_MODEL = "swiss-ai/apertus-8b-instruct"

# HTTP status codes that mean "try again later" rather than "your request
# is wrong". These are worth retrying with backoff.
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

# Retry policy
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 5.0
BACKOFF_MULTIPLIER = 2.0


class ApertusClient(BaseClient):
    def __init__(self):
        self.url = "https://api.publicai.co/v1/chat/completions"

    def query(self, prompt: str, model: str = APERTUS_DEFAULT_MODEL) -> str:
        api_key = get_publicai_key()
        if not api_key:
            return "[ERROR] PUBLICAI_API_KEY not set"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "BGer-OverRefusal-Benchmark/1.0 (HES-SO Valais research)",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }

        backoff = INITIAL_BACKOFF_SECONDS
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(
                    self.url, json=payload, headers=headers, timeout=180
                )

                # Transient server-side error: retry with backoff
                if response.status_code in TRANSIENT_STATUS_CODES:
                    last_error = f"HTTP {response.status_code}"
                    if attempt < MAX_RETRIES:
                        print(f"    [Apertus retry {attempt}/{MAX_RETRIES} "
                              f"after {last_error}, waiting {backoff:.0f}s]")
                        time.sleep(backoff)
                        backoff *= BACKOFF_MULTIPLIER
                        continue
                    return f"[ERROR] Apertus {last_error} after {MAX_RETRIES} retries"

                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]

            except requests.exceptions.Timeout as exc:
                # Client-side timeout — also worth retrying
                last_error = f"Timeout: {exc}"
                if attempt < MAX_RETRIES:
                    print(f"    [Apertus retry {attempt}/{MAX_RETRIES} "
                          f"after timeout, waiting {backoff:.0f}s]")
                    time.sleep(backoff)
                    backoff *= BACKOFF_MULTIPLIER
                    continue
                return f"[ERROR] Apertus timeout after {MAX_RETRIES} retries"

            except Exception as exc:
                # Non-retryable error (auth, malformed request, etc.)
                return f"[ERROR] {exc}"

        return f"[ERROR] Apertus failed after {MAX_RETRIES} retries: {last_error}"