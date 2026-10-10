"""
llm.py — one function, complete(system, user), over plain HTTP (no SDK needed).

Configure in .env:
  LLM_PROVIDER   anthropic (default) | openai   ("openai" = any OpenAI-compatible API)
  LLM_API_KEY    your key
  LLM_MODEL      model name (check your provider's docs)
  LLM_BASE_URL   openai mode only, e.g. https://api.openai.com/v1, https://api.groq.com/openai/v1,
                 http://localhost:11434/v1 (Ollama), https://api.sarvam.ai/v1
  LLM_AUTH_HEADER  openai mode only. Default sends "Authorization: Bearer <key>".
                 Set to e.g. api-subscription-key to send the raw key in that header instead (Sarvam).
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4o-mini"}
TIMEOUT = 60


class LLMError(Exception):
    """A failure we can explain to the user in one sentence."""


def _config() -> dict:
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    key = os.getenv("LLM_API_KEY") or (os.getenv("ANTHROPIC_API_KEY") if provider == "anthropic" else None)
    return {
        "provider": provider,
        "key": key,
        "model": os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(provider, ""),
        "base_url": (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
        "auth_header": os.getenv("LLM_AUTH_HEADER", "Authorization"),
    }


def is_configured() -> bool:
    c = _config()
    # local servers (Ollama) don't need a key
    local = c["provider"] == "openai" and "localhost" in c["base_url"]
    return bool(c["key"]) or local


def describe() -> str:
    c = _config()
    return f"{c['provider']} · {c['model']}"


def complete(system: str, user: str, max_tokens: int = 900) -> str:
    c = _config()
    if c["provider"] not in ("anthropic", "openai"):
        raise LLMError(f"Unknown LLM_PROVIDER '{c['provider']}' (use 'anthropic' or 'openai').")
    if not is_configured():
        raise LLMError("No LLM configured. Set LLM_PROVIDER, LLM_API_KEY and LLM_MODEL in .env.")

    if c["provider"] == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": c["key"], "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        body = {"model": c["model"], "max_tokens": max_tokens, "system": system,
                "messages": [{"role": "user", "content": user}]}
    else:
        url = f"{c['base_url']}/chat/completions"
        headers = {"content-type": "application/json"}
        if c["key"]:
            if c["auth_header"].lower() == "authorization":
                headers["Authorization"] = f"Bearer {c['key']}"
            else:
                headers[c["auth_header"]] = c["key"]
        body = {"model": c["model"], "max_tokens": max_tokens, "temperature": 0.2,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
    except requests.Timeout:
        raise LLMError("The LLM took too long to respond. Try again.")
    except requests.RequestException as e:
        raise LLMError(f"Couldn't reach the LLM service ({type(e).__name__}).")

    if resp.status_code in (401, 403):
        raise LLMError("The LLM API key was rejected. Check LLM_API_KEY.")
    if resp.status_code == 429:
        raise LLMError("The LLM is rate-limiting requests. Wait a moment and retry.")
    if resp.status_code >= 400:
        raise LLMError(f"LLM request failed ({resp.status_code}): {resp.text[:200]}")

    try:
        data = resp.json()
        if c["provider"] == "anthropic":
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        else:
            text = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError("The LLM returned a response I couldn't read.")
    text = (text or "").strip()
    if not text:
        raise LLMError("The LLM returned an empty answer.")
    return text