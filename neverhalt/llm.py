"""Minimal streaming client for an OpenAI-compatible /chat/completions endpoint (stdlib only).

Default: Ripple-65B Preview through OpenRouter. RIPPLE_BASE_URL / RIPPLE_MODEL / RIPPLE_API_KEY point it elsewhere.
"""
from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

OPENROUTER_URL = "https://openrouter.ai/api/v1"
RIPPLE_MODEL = "ricursiveai/ripple-65b-preview"


class LLMError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}


def _describe(body: str) -> str:
    """OpenRouter error JSON -> 'Provider returned error · GMICloud 502 · PrimeIntellect 429'; raw text otherwise."""
    try:
        err = json.loads(body).get("error") or {}
    except (ValueError, AttributeError):
        return body[:300]
    meta = err.get("metadata") or {}
    parts = [str(err.get("message", "error"))]
    if meta.get("provider_name"):
        parts.append(f"{meta['provider_name']} {err.get('code', '')}".strip())
    parts += [f"{p.get('provider_name')} {p.get('code')}" for p in meta.get("previous_errors") or []]
    return " · ".join(parts)[:300]


@dataclass
class Config:
    base_url: str
    api_key: str
    model: str
    reasoning: str  # off | low | medium | high
    max_tokens: int
    temperature: float | None
    providers: list[str]  # OpenRouter providers allowed to serve the model; empty = any


def load_config(root: Path) -> Config:
    """Environment variables win over KEY=VALUE lines in root/.env."""
    env = dict(os.environ)
    dotenv = root / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#") and value.strip():
                env.setdefault(key.strip(), value.split(" #")[0].strip().strip("'\""))  # drop inline comments
    key = env.get("RIPPLE_API_KEY") or env.get("OPENROUTER_API_KEY") or ""
    if not key:
        raise LLMError(f"no API key: set OPENROUTER_API_KEY in {dotenv}")
    temperature = env.get("RIPPLE_TEMPERATURE")
    return Config(
        base_url=env.get("RIPPLE_BASE_URL", OPENROUTER_URL).rstrip("/"),
        api_key=key,
        model=env.get("RIPPLE_MODEL", RIPPLE_MODEL),
        reasoning=env.get("RIPPLE_REASONING", "off").lower(),
        max_tokens=int(env.get("RIPPLE_MAX_TOKENS", "24000")),  # room for Ripple's thinking plus the code
        temperature=float(temperature) if temperature else None,
        # GMICloud spent a whole 6000-token budget on output it never returned (2026-11-13), so it is not allowed
        providers=[p.strip() for p in env.get("RIPPLE_PROVIDERS", "PrimeIntellect,Together").split(",") if p.strip()],
    )


def request(cfg: Config, path: str, body: dict | None = None, timeout: float = 120):
    req = urllib.request.Request(
        cfg.base_url + path, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json",
                 "Accept": "text/event-stream" if body and body.get("stream") else "application/json",
                 "User-Agent": "neverhalt/0.1", "X-Title": "NEVERHALT"})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code}: {_describe(e.read().decode(errors='replace'))}", e.code in RETRYABLE) from None
    except (urllib.error.URLError, OSError) as e:
        raise LLMError(f"cannot reach {cfg.base_url}: {e}", True) from None


class _ThinkSplitter:
    """Routes inline <think>…</think> spans to the reasoning callback, tolerating tags split across chunks."""

    def __init__(self, on_content, on_reasoning):
        self.sinks = {False: on_content, True: on_reasoning}
        self.thinking, self.buf = False, ""

    def feed(self, text: str, final: bool = False):
        self.buf += text
        while True:
            tag = "</think>" if self.thinking else "<think>"
            at = self.buf.find(tag)
            if at >= 0:
                if at:
                    self.sinks[self.thinking](self.buf[:at])
                self.buf = self.buf[at + len(tag):]
                self.thinking = not self.thinking
                continue
            keep = 0 if final else next((n for n in range(len(tag) - 1, 0, -1) if self.buf.endswith(tag[:n])), 0)
            if len(self.buf) > keep:
                self.sinks[self.thinking](self.buf[:len(self.buf) - keep])
                self.buf = self.buf[len(self.buf) - keep:]
            return


def stream_chat(cfg: Config, messages: list[dict], on_content, on_reasoning, extra: dict | None = None) -> dict:
    """-> {"content", "reasoning", "prompt_tokens", "completion_tokens", "cost", "provider", "seconds", "finish", "estimated"}"""
    body = {"model": cfg.model, "messages": messages, "max_tokens": cfg.max_tokens, "stream": True,
            "usage": {"include": True}}  # OpenRouter puts token counts and cost in the final chunk
    if cfg.temperature is not None:
        body["temperature"] = cfg.temperature
    if cfg.reasoning in ("low", "medium", "high"):
        body["reasoning"] = {"effort": cfg.reasoning}
    if cfg.providers and "openrouter.ai" in cfg.base_url:
        body["provider"] = {"only": cfg.providers}
    body.update(extra or {})  # e.g. response_format
    content, reasoning = [], []
    splitter = _ThinkSplitter(lambda t: (content.append(t), on_content(t)), lambda t: (reasoning.append(t), on_reasoning(t)))
    usage, finish, provider, t0 = {}, None, None, time.time()
    try:
        with request(cfg, "/chat/completions", body, timeout=300) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("error"):
                    code = chunk["error"].get("code")
                    raise LLMError(f"stream error: {_describe(json.dumps(chunk))}", code is None or code in RETRYABLE)
                usage = chunk.get("usage") or usage
                provider = chunk.get("provider") or provider
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    thought = delta.get("reasoning_content") or delta.get("reasoning")
                    if isinstance(thought, str) and thought:
                        reasoning.append(thought)
                        on_reasoning(thought)
                    if delta.get("content"):
                        splitter.feed(delta["content"])
                    finish = choice.get("finish_reason") or finish
    except (OSError, ValueError) as e:  # dropped connection, read timeout, malformed chunk
        raise LLMError(f"stream from {cfg.base_url} broke: {type(e).__name__}: {e}", True) from None
    splitter.feed("", final=True)
    text, thoughts = "".join(content), "".join(reasoning)
    return {"content": text, "reasoning": thoughts, "seconds": time.time() - t0, "finish": finish,
            "estimated": not usage, "cost": float(usage.get("cost") or 0.0), "provider": provider,
            "prompt_tokens": usage.get("prompt_tokens") or sum(len(m["content"]) for m in messages) // 4,
            "completion_tokens": usage.get("completion_tokens") or (len(text) + len(thoughts)) // 4}


def chat(cfg: Config, messages: list[dict], on_content, on_reasoning, on_retry, patience: float = 1200.0,
         extra: dict | None = None) -> dict:
    """stream_chat, retrying rate limits and transient failures with jittered backoff for up to `patience` seconds."""
    deadline, attempt = time.time() + patience, 0
    while True:
        try:
            return stream_chat(cfg, messages, on_content, on_reasoning, extra)
        except LLMError as e:
            attempt += 1
            delay = min(60.0, 2.0 ** attempt) * random.uniform(0.7, 1.3)
            if not e.retryable or time.time() + delay > deadline:
                raise
            on_retry(delay, e)
            time.sleep(delay)


def doctor(cfg: Config) -> bool:
    print(f"endpoint  {cfg.base_url}\nmodel     {cfg.model}\nkey       …{cfg.api_key[-4:]}\nreasoning {cfg.reasoning}")
    if "openrouter.ai" in cfg.base_url:
        try:
            with request(cfg, "/key", timeout=20) as resp:
                info = json.load(resp).get("data") or {}
            print(f"account   used ${float(info.get('usage') or 0):.2f} · limit {info.get('limit')} · free tier {info.get('is_free_tier')}")
        except LLMError as e:
            print(f"account   key check FAILED: {str(e)[:300]}")
            return False
    try:
        first = []
        mark = lambda _: first or first.append(time.time())
        t0 = time.time()
        r = stream_chat(cfg, [{"role": "user", "content": "Write a Python function that reverses a string. Code only."}], mark, mark)
        ttft = (first[0] - t0) if first else r["seconds"]
        speed = r["completion_tokens"] / max(r["seconds"] - ttft, 1e-3)
        print(f"chat      OK via {r['provider'] or 'unknown provider'} · first token {ttft:.1f}s · {r['completion_tokens']} tokens "
              f"in {r['seconds']:.1f}s (~{speed:.0f} tok/s{', token counts estimated' if r['estimated'] else ''}) · "
              f"${r['cost']:.5f} · reasoning {'present' if r['reasoning'] else 'absent'}")
        print("reply     " + r["content"].strip().replace("\n", "\n          ")[:400])
        return True
    except LLMError as e:
        print(f"chat      FAILED\n          {e}")
        return False
