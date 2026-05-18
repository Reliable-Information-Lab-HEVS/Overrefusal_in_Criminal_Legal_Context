"""Mistral API client (chat-completions endpoint)."""

import requests

from over_refusal.config import MISTRAL_DEFAULT_MODEL, get_mistral_key
from .base import BaseClient


class MistralClient(BaseClient):
    def __init__(self):
        self.url = "https://api.mistral.ai/v1/chat/completions"

    def query(self, prompt: str, model: str = MISTRAL_DEFAULT_MODEL) -> str:
        api_key = get_mistral_key()
        if not api_key:
            return "[ERROR] MISTRAL_API_KEY not set"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }

        try:
            response = requests.post(self.url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            return f"[ERROR] {exc}"
