"""Client for a hosted LLM behind a LiteLLM proxy (e.g. the armasuisse
internal gateway at litellm.intlab.ch), OpenAI-compatible /v1/chat/completions.

Deliberately kept OUTSIDE over_refusal/clients/ and NOT wired into
EvaluationRunner. This project's pipeline is on-premises only by design
(see over_refusal/evaluation.py's docstring and CLAUDE.md) -- every prompt
sent through this client leaves that boundary and goes to a remote gateway
instead of a local Ollama server. Do not point this at confidential or
real-document datasets (BGer judgments, defense white papers, etc.)
without checking your project's data-handling policy first; it's meant for
a standalone side-comparison against small on-premises models, not as a
new backend for the paper's actual evaluation.

No API key is read from anywhere but the environment -- never hardcode one
here or pass it on the command line (shell history, process list).
"""

import os

import requests

DEFAULT_BASE_URL = "https://litellm.intlab.ch"
DEFAULT_TIMEOUT = 120


class LiteLLMClient:
    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        # Deferred check (at query() time, not here): EvaluationRunner-style
        # runners often construct every client up front even if a given run
        # never calls it, so raising in __init__ would be too eager. This
        # class isn't used that way today, but matching that safer pattern
        # costs nothing.
        self.api_key = api_key or os.environ.get("LITELLM_API_KEY")
        self.base_url = (base_url or os.environ.get("LITELLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    def query(self, prompt: str, model: str, max_tokens: int = 1024) -> str:
        """Send one prompt as a single user message. Returns the response
        text, or a "[ERROR] ..." string on any failure (never raises) --
        matching over_refusal.clients.OllamaClient's convention, so this
        drops into the same result-row / refusal-detection code unchanged.

        max_tokens matters more here than for a normal chat model: reasoning
        models (Kimi K2.6 included) spend part of the budget on an internal
        reasoning_content trace before writing the final content. Too low a
        max_tokens truncates mid-reasoning and content comes back null/empty
        -- that's reported as an [ERROR], not silently treated as an empty
        (and therefore not-a-refusal) response.
        """
        if not self.api_key:
            return "[ERROR] LITELLM_API_KEY not set"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            content = choice.get("message", {}).get("content")
            if not content:
                finish_reason = choice.get("finish_reason")
                return (
                    f"[ERROR] empty content (finish_reason={finish_reason}); "
                    f"a reasoning model likely spent max_tokens={max_tokens} "
                    f"entirely on reasoning_content -- raise max_tokens"
                )
            return content
        except Exception as exc:
            return f"[ERROR] {exc}"
