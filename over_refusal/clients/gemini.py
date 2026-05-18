"""Gemini client.

Refs:
- Safety settings (categories + thresholds):
  https://ai.google.dev/gemini-api/docs/safety-settings
- Built-in non-configurable filters (PROHIBITED_CONTENT, etc.):
  https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/configure-safety-filters
- Response schema (candidates, finishReason, promptFeedback):
  https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference

The four HARM_CATEGORY_* filters are user-adjustable via safetySettings.
PROHIBITED_CONTENT (CSAM, etc.) is not configurable and is enforced
server-side regardless of safetySettings. We treat server-side blocks as
model-level refusals so they appear in is_refused stats rather than in
is_error.
"""

import json
import os
from typing import Optional

import requests

from .base import BaseClient


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

SAFETY_CATEGORIES = [
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
]

REFUSAL_FINISH_REASONS = {
    "SAFETY",
    "PROHIBITED_CONTENT",
    "RECITATION",
    "BLOCKLIST",
    "SPII",
    "OTHER",
}


class GeminiClient(BaseClient):
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 60):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

    def query(self, prompt: str, model: str) -> str:
        url = f"{GEMINI_API_BASE}/{model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "safetySettings": [
                {"category": cat, "threshold": "BLOCK_NONE"}
                for cat in SAFETY_CATEGORIES
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 2048,
            },
        }

        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return f"[ERROR] {exc}"

        if resp.status_code != 200:
            return f"[ERROR] HTTP {resp.status_code}: {resp.text[:300]}"

        try:
            data = resp.json()
        except ValueError:
            return f"[ERROR] Invalid JSON response: {resp.text[:300]}"

        # Prompt-level block
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        if block_reason:
            return (
                f"I cannot provide a response to this request. "
                f"[Gemini refusal: prompt blockReason={block_reason}]"
            )

        # Candidate-level outcome
        candidates = data.get("candidates") or []
        if candidates:
            cand = candidates[0]
            finish_reason = cand.get("finishReason")
            parts = (cand.get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()

            if text:
                return text
            if finish_reason in REFUSAL_FINISH_REASONS:
                return (
                    f"I cannot provide a response to this request. "
                    f"[Gemini refusal: finishReason={finish_reason}]"
                )
            return (
                f"[ERROR] Empty content (finishReason={finish_reason})"
            )

        return f"[ERROR] No candidates returned. Raw: {json.dumps(data)[:300]}"