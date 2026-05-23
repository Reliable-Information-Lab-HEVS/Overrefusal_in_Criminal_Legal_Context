"""Ollama local-server client (no API key needed)."""

import requests

from refusal_eval.config import OLLAMA_TIMEOUT, OLLAMA_URL, TEMPERATURE
from .base import BaseClient


class OllamaClient(BaseClient):
    def __init__(self, base_url: str = OLLAMA_URL, timeout: int = OLLAMA_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout

    def query(self, prompt: str, model: str) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": TEMPERATURE},
        }
        try:
            response = requests.post(self.base_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as exc:
            return f"[ERROR] {exc}"
