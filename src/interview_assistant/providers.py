"""OpenAI-compatible chat provider abstraction.

A single `chat()` covers Groq / OpenAI / DeepSeek / OpenRouter / Azure / vLLM /
n1n.ai / anything else that speaks the OpenAI Chat Completions API. Optional
fallback endpoint kicks in on 429/503.
"""
from __future__ import annotations

import json
from typing import Any, Iterator

import httpx


PRESETS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "fast_model": "llama-3.1-8b-instant",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "fast_model": "gpt-4o-mini",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct",
        "fast_model": "meta-llama/llama-3.1-8b-instruct",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "fast_model": "deepseek-chat",
    },
    "n1n": {
        "base_url": "https://api.n1n.ai/v1",
        "model": "claude-haiku-4-5-20251001",
        "fast_model": "qwen-flash",
    },
}


def _client(base_url: str, proxy: str = "", timeout: float = 30.0) -> httpx.Client:
    kw: dict[str, Any] = {"timeout": timeout, "base_url": base_url.rstrip("/")}
    if proxy:
        kw["proxy"] = proxy
    return httpx.Client(**kw)


def ping(base_url: str, api_key: str, model: str, proxy: str = "") -> tuple[bool, str]:
    """Cheap connectivity check — returns (ok, error)."""
    try:
        with _client(base_url, proxy, timeout=10.0) as c:
            r = c.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "temperature": 0,
                },
            )
        if r.status_code == 200:
            return True, ""
        return False, f"HTTP {r.status_code}: {r.text[:160]}"
    except Exception as e:
        return False, str(e)


def chat(
    cfg_chat: dict,
    messages: list[dict],
    *,
    fast: bool = False,
    stream: bool = True,
    max_tokens: int = 2000,
    temperature: float = 0.3,
) -> Iterator[str] | str:
    """Call chat completions. If stream, yields delta strings; else returns full text.

    On 429/503 from the primary endpoint, falls back to fallback_* if configured.
    """
    primary = (
        cfg_chat["base_url"],
        cfg_chat["api_key"],
        cfg_chat["fast_model"] if fast else cfg_chat["model"],
    )
    fallback = (
        cfg_chat.get("fallback_base_url", ""),
        cfg_chat.get("fallback_api_key", ""),
        cfg_chat.get("fallback_model", "") or (cfg_chat["fast_model"] if fast else cfg_chat["model"]),
    )
    proxy = cfg_chat.get("http_proxy", "")

    def _do(base, key, model):
        return _request(base, key, model, messages, stream, max_tokens, temperature, proxy)

    try:
        return _do(*primary)
    except _RetryableError as e:
        if all(fallback[:2]):
            return _do(*fallback)
        raise RuntimeError(f"primary failed and no fallback: {e}") from e


class _RetryableError(Exception):
    pass


def _request(base_url, api_key, model, messages, stream, max_tokens, temperature, proxy):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    client = _client(base_url, proxy, timeout=60.0 if stream else 30.0)
    if not stream:
        try:
            r = client.post("/chat/completions", headers=headers, json=payload)
            if r.status_code in (429, 503):
                raise _RetryableError(f"HTTP {r.status_code}")
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
            return data["choices"][0]["message"]["content"]
        finally:
            client.close()

    def _gen():
        try:
            with client.stream("POST", "/chat/completions", headers=headers, json=payload) as r:
                if r.status_code in (429, 503):
                    raise _RetryableError(f"HTTP {r.status_code}")
                if r.status_code != 200:
                    body = r.read().decode("utf-8", errors="ignore")
                    raise RuntimeError(f"HTTP {r.status_code}: {body[:200]}")
                for line in r.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        finally:
            client.close()

    return _gen()
