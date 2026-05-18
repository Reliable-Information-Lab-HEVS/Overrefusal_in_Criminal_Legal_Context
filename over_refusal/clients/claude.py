"""Anthropic Claude API client."""

import requests

from over_refusal.config import CLAUDE_DEFAULT_MODEL, get_anthropic_key
from .base import BaseClient


class ClaudeClient(BaseClient):
    def __init__(self):
        self.url = "https://api.anthropic.com/v1/messages"

    def query(self, prompt: str, model: str = CLAUDE_DEFAULT_MODEL) -> str:
        api_key = get_anthropic_key()
        if not api_key:
            return "[ERROR] ANTHROPIC_API_KEY not set"

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }

        try:
            response = requests.post(self.url, json=payload, headers=headers, timeout=90)
            if not response.ok:
                return f"[ERROR] HTTP {response.status_code} | {response.text}"

            data = response.json()
            # Claude returns a list of content blocks; we keep only text blocks
            parts = data.get("content", [])
            text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
            final_text = "\n".join(text_parts).strip()
            return final_text if final_text else "[ERROR] No text content returned"

        except requests.exceptions.RequestException as exc:
            return f"[ERROR] Request failed: {exc}"
        except Exception as exc:
            return f"[ERROR] Unexpected: {exc}"
