"""Generic OpenAI-compatible chat-completions client.

One client for every backend that speaks the OpenAI ``/chat/completions`` wire
format: OpenAI, Mistral, the Public AI gateway (Apertus), a local vLLM server,
or any internal endpoint the Federal Tribunal points it at. Per-provider
differences are expressed as configuration in ``models.yaml`` (base_url, which
env var holds the key, extra headers, timeout, retry policy) instead of as
separate Python classes.

This collapses the former per-vendor clients (OpenAIClient / MistralClient /
ApertusClient), which were byte-for-byte the same request except for those few
fields. The retired files are kept under ``clients/legacy/`` for provenance.

Behavior contract (unchanged from the original per-vendor clients):
  * temperature is always 0.0;
  * a missing API key returns ``"[ERROR] <ENV_VAR> not set"``;
  * any transport/parse failure returns an ``"[ERROR] ..."`` string, never raises;
  * when a retry policy is configured, transient HTTP statuses (429/5xx) and
    timeouts are retried with exponential backoff (used for the Public AI
    gateway, which returns occasional 504s under load).
"""

import os
import time
from typing import Dict, Optional

import requests

from .base import BaseClient


# HTTP status codes that mean "try again later" rather than "your request is
# wrong". Only retried when a retry policy is configured for the model.
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class OpenAICompatibleClient(BaseClient):
    def __init__(
        self,
        base_url: str,
        api_key_env: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 90,
        retry: Optional[Dict] = None,
    ):
        self.base_url = base_url
        self.api_key_env = api_key_env
        self.extra_headers = dict(headers) if headers else {}
        self.timeout = timeout
        # retry is None (single attempt) or a dict with keys:
        #   max_retries, initial_backoff_seconds, backoff_multiplier
        self.retry = retry

    def query(self, prompt: str, model: str) -> str:
        api_key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        if self.api_key_env and not api_key:
            return f"[ERROR] {self.api_key_env} not set"

        headers = {"Content-Type": "application/json", **self.extra_headers}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }

        max_retries = int(self.retry["max_retries"]) if self.retry else 1
        backoff = float(self.retry.get("initial_backoff_seconds", 5.0)) if self.retry else 0.0
        multiplier = float(self.retry.get("backoff_multiplier", 2.0)) if self.retry else 1.0

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    self.base_url, json=payload, headers=headers, timeout=self.timeout
                )

                # Transient server-side error: retry with backoff (if enabled)
                if self.retry and response.status_code in TRANSIENT_STATUS_CODES:
                    last_error = f"HTTP {response.status_code}"
                    if attempt < max_retries:
                        print(f"    [retry {attempt}/{max_retries} after {last_error}, "
                              f"waiting {backoff:.0f}s]")
                        time.sleep(backoff)
                        backoff *= multiplier
                        continue
                    return f"[ERROR] {last_error} after {max_retries} retries"

                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]

            except requests.exceptions.Timeout as exc:
                # Client-side timeout — also worth retrying when enabled
                last_error = f"Timeout: {exc}"
                if self.retry and attempt < max_retries:
                    print(f"    [retry {attempt}/{max_retries} after timeout, "
                          f"waiting {backoff:.0f}s]")
                    time.sleep(backoff)
                    backoff *= multiplier
                    continue
                return f"[ERROR] {last_error}"

            except Exception as exc:
                # Non-retryable error (auth, malformed request, parse failure, ...)
                return f"[ERROR] {exc}"

        return f"[ERROR] failed after {max_retries} retries: {last_error}"
