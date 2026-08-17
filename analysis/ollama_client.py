"""Thin wrapper over Ollama's local REST API (https://localhost:11434 by default).

Kept intentionally minimal — no provider abstraction yet. If a second
provider (cloud or another local runtime) is ever added, this is the module
that would be generalized into one. Shared by both the `analysis` app
(job-search insights, JSON output) and the `assistant` app (cover
letters/interview answers, plain-text output) rather than duplicated —
imported directly as `analysis.ollama_client` from `assistant/views.py`.
"""

import json

import requests
from django.conf import settings

REQUEST_TIMEOUT_SECONDS = 120


class OllamaUnavailableError(Exception):
    pass


class OllamaResponseParseError(Exception):
    """Raised when json_mode=True but Ollama's response wasn't valid JSON
    despite format="json". Carries the raw text so each caller can build
    its own fallback shape — this module has no opinion on what a caller's
    JSON response should look like, so it doesn't guess one.
    """

    def __init__(self, raw_text):
        self.raw_text = raw_text
        super().__init__("Ollama did not return valid JSON")


def generate(prompt, json_mode=True, temperature=None):
    """Calls Ollama with `prompt`.

    json_mode=True (default): requests Ollama's format="json" constraint and
    parses the response, returning a dict/list. Raises
    OllamaResponseParseError (carrying the raw text) if parsing fails.

    json_mode=False: no format constraint — returns the raw text response
    directly (stripped). Use this for natural-language output (a cover
    letter, an interview answer) where forcing JSON would fight the model
    into producing awkward, quoted-string prose instead of a clean block of
    text.

    temperature: passed through to Ollama's options.temperature when given
    (Ollama's own default otherwise, typically ~0.8). Confirmed live while
    building the assistant app: llama3.1:8b invents plausible-sounding but
    entirely fabricated work history/metrics fairly readily at default
    temperature, even when explicitly instructed not to — assistant/prompts.py
    passes a low value for cover-letter/answer generation as one mitigation
    (alongside the prompt wording itself) to make the model stick closer to
    the given profile rather than embellishing. Not a complete fix on its
    own — see assistant/prompts.py's ANTI_FABRICATION_RULE and CLAUDE.md's
    documented known limitation here.
    """
    try:
        response = requests.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                **({"format": "json"} if json_mode else {}),
                **({"options": {"temperature": temperature}} if temperature is not None else {}),
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise OllamaUnavailableError(
            f"Couldn't reach Ollama at {settings.OLLAMA_URL}. Is it running (`ollama serve`)?"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise OllamaUnavailableError(f"Ollama request failed: {exc}") from exc

    raw_text = response.json().get("response", "")
    if not json_mode:
        return raw_text.strip()

    try:
        return json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        raise OllamaResponseParseError(raw_text)
