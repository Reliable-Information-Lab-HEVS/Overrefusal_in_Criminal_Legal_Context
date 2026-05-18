"""OpenAI API client (chat-completions endpoint)."""

import requests

from over_refusal.config import OPENAI_DEFAULT_MODEL, get_openai_key
from .base import BaseClient


class OpenAIClient(BaseClient):
    def __init__(self):
        self.url = "https://api.openai.com/v1/chat/completions"

    def query(self, prompt: str, model: str = OPENAI_DEFAULT_MODEL) -> str:
        api_key = get_openai_key()
        if not api_key:
            return "[ERROR] OPENAI_API_KEY not set"

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
            response = requests.post(self.url, json=payload, headers=headers, timeout=90)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            return f"[ERROR] {exc}"
