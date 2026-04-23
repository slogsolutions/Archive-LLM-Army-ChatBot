from __future__ import annotations
import json
import requests
from typing import Iterator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL  = "http://localhost:11434"
DEFAULT_MODEL    = "llama3:latest"
REQUEST_TIMEOUT  = 120   # seconds — llama3 on CPU can be slow


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chat(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    stream: bool = False,
    temperature: float = 0.2,    # Low → factual; army docs need precision
    max_tokens: int = 1024,
) -> str | Iterator[str]:
    """
    Send a prompt to Ollama and return the response.

    Args:
        prompt      : User-turn prompt (includes injected context)
        system      : System prompt (rules, role, format guidance)
        model       : Ollama model name (e.g. "llama3:latest")
        stream      : If True, returns a token iterator (for SSE endpoints)
        temperature : Sampling temperature (0.0–1.0)
        max_tokens  : Maximum tokens to generate

    Returns:
        str           — full response text (stream=False)
        Iterator[str] — token-by-token generator (stream=True)

    Raises:
        requests.HTTPError  — if Ollama returns a non-200 status
        RuntimeError        — if Ollama is not reachable
    """
    payload = {
        "model":   model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "stream": stream,
        "options": {
            "temperature":  temperature,
            "num_predict":  max_tokens,
        },
    }

    if stream:
        return _stream(payload)

    return _blocking(payload)


def is_ollama_running() -> bool:
    """
    Quick health check — returns True if Ollama is up and reachable.
    Use this as a guard before calling chat().
    """
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def list_models() -> list[str]:
    """Return the names of locally available Ollama models."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _blocking(payload: dict) -> str:
    """Single-shot request — wait for full response."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.ConnectionError:
        raise RuntimeError(
            "Cannot connect to Ollama. "
            "Start it with: ollama serve"
        )

    data = resp.json()
    return data["message"]["content"].strip()


def _stream(payload: dict) -> Iterator[str]:
    """Streaming request — yields tokens as they arrive."""
    try:
        with requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
                # Ollama sends {"done": true} as the last chunk
                if chunk.get("done"):
                    break
    except requests.ConnectionError:
        raise RuntimeError(
            "Cannot connect to Ollama. "
            "Start it with: ollama serve"
        )