"""Ollama local-server client (no API key needed)."""

import requests

from over_refusal.config import DEFAULT_OLLAMA_TIMEOUT, OLLAMA_URL
from .base import BaseClient


class OllamaClient(BaseClient):
    def __init__(self, base_url: str = OLLAMA_URL, timeout: int = DEFAULT_OLLAMA_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout

    def query(self, prompt: str, model: str) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0},
        }

        try:
            response = requests.post(self.base_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as exc:
            return f"[ERROR] {exc}"
