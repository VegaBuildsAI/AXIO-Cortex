"""
AXIO Core - Model Clients & Router
Provides:
  OllamaClient  -> streaming chat, generate, and tool-calling via local Ollama
  ClaudeClient  -> chat and tool-calling via Anthropic API
  ModelRouter   -> delegates to core.router for keyword-based routing
"""

import json
import time
import requests
from typing import Optional

from .config import (
    OLLAMA_HOST, OLLAMA_CHAT, OLLAMA_GEN, OLLAMA_TAGS,
    OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT,
    CLAUDE_API_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS,
    RETRY_ATTEMPTS, RETRY_BACKOFF, TIMEOUT, PROMPT_CACHE,
)


# ─────────────────────────────────────────────────────────
#  OLLAMA CLIENT
# ─────────────────────────────────────────────────────────

class OllamaClient:
    """Connects to a local Ollama instance with retry logic."""

    def __init__(self, host=None):
        self.host = (host or OLLAMA_HOST).rstrip("/")
        self._thinking_cache = {}
        self.last_usage = None
        self.last_done_reason = None

    @staticmethod
    def _generation_options(extra=None):
        """Return bounded defaults while allowing a caller to narrow them."""
        options = {
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT,
        }
        options.update(extra or {})
        return options

    def _supports_thinking(self, model):
        """True if the model advertises the 'thinking' capability (qwen3 dense).

        Cached per model. Used to send think:false so thinking tokens don't
        consume the output budget / slow responses (ASSESS-004). Models that
        do not advertise 'thinking' (e.g. gemma4:12b) are left untouched.
        """
        if model in self._thinking_cache:
            return self._thinking_cache[model]
        supported = False
        try:
            r = requests.post(
                f"{self.host}/api/show", json={"model": model}, timeout=5
            )
            if r.ok:
                supported = "thinking" in (r.json().get("capabilities") or [])
        except Exception:
            supported = False
        self._thinking_cache[model] = supported
        return supported

    def is_running(self):
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self):
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            return r.json().get("models", [])
        except Exception:
            return []

    def chat_stream(self, model, messages, print_output=True):
        """Stream a chat response and optionally print tokens live."""
        full = ""
        self.last_usage = None
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": self._generation_options(),
        }
        if self._supports_thinking(model):
            payload["think"] = False
        for attempt in range(RETRY_ATTEMPTS):
            try:
                r = requests.post(
                    f"{self.host}/api/chat",
                    json=payload,
                    stream=True, timeout=TIMEOUT,
                )
                r.raise_for_status()
                for line in r.iter_lines():
                    if line:
                        data  = json.loads(line)
                        chunk = data.get("message", {}).get("content", "")
                        full += chunk
                        if print_output:
                            print(chunk, end="", flush=True)
                        if data.get("done"):
                            self.last_done_reason = data.get("done_reason")
                            self.last_usage = {
                                "input": int(data.get("prompt_eval_count", 0) or 0),
                                "output": int(data.get("eval_count", 0) or 0),
                            }
                            break
                if print_output:
                    print()
                return full
            except requests.exceptions.ConnectionError:
                raise
            except Exception:
                if attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)
                else:
                    raise
        return full

    def generate_stream(self, model, prompt, system="", options=None):
        """Stream a generate (non-chat) response. Returns (text, elapsed_s)."""
        payload = {
            "model":   model,
            "prompt":  (system + "\n\n" + prompt) if system else prompt,
            "stream":  True,
            "options": self._generation_options(
                options or {"temperature": 0.2, "top_p": 0.85}
            ),
        }
        if self._supports_thinking(model):
            payload["think"] = False
        start = time.time()
        r = requests.post(OLLAMA_GEN, json=payload, stream=True, timeout=TIMEOUT)
        r.raise_for_status()
        full = ""
        print(f"\n\033[36m[{model}]\033[0m ", end="", flush=True)
        for line in r.iter_lines():
            if line:
                chunk = json.loads(line)
                token = chunk.get("response", "")
                print(token, end="", flush=True)
                full += token
                if chunk.get("done"):
                    self.last_done_reason = chunk.get("done_reason")
                    break
        elapsed = round(time.time() - start, 2)
        print(f"\n\033[90m[{elapsed}s]\033[0m")
        return full, elapsed

    def tool_call(self, model, messages, tools):
        """Send a tool-calling request to Ollama (non-streaming)."""
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": self._generation_options(),
        }
        if self._supports_thinking(model):
            payload["think"] = False
        for attempt in range(RETRY_ATTEMPTS):
            try:
                r = requests.post(
                    f"{self.host}/api/chat",
                    json=payload,
                    timeout=TIMEOUT,
                )
                r.raise_for_status()
                data = r.json()
                self.last_done_reason = data.get("done_reason")
                self.last_usage = {
                    "input": int(data.get("prompt_eval_count", 0) or 0),
                    "output": int(data.get("eval_count", 0) or 0),
                }
                return data
            except requests.exceptions.ReadTimeout:
                if attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)
                else:
                    raise
            except requests.exceptions.HTTPError as exc:
                response = exc.response
                status = int(getattr(response, "status_code", 0) or 0)
                body = str(getattr(response, "text", "") or "").strip().replace("\n", " ")[:800]
                if status >= 500 and attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)
                    continue
                detail = f"HTTP {status}" if status else "HTTP error"
                if body:
                    detail += f": {body}"
                raise RuntimeError(f"Ollama tool call failed after {attempt + 1} attempt(s): {detail}") from exc
        return {}

    def embed(self, model, text):
        """Generate an embedding vector via Ollama /api/embeddings."""
        try:
            r = requests.post(
                f"{self.host}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=60,
            )
            r.raise_for_status()
            return r.json().get("embedding", [])
        except Exception:
            return []


# ─────────────────────────────────────────────────────────
#  CLAUDE CLIENT
# ─────────────────────────────────────────────────────────

class ClaudeClient:
    """Wraps the Anthropic SDK for chat and tool-calling.

    Model + effort are read from core.claude_runtime on every call (unless an
    explicit model was passed), so in-app `model`/`effort` switches take effect
    on the next request. All requests use adaptive thinking + output_config.effort.
    """

    def __init__(self, model: str = None):
        self._explicit_model = model   # None -> follow the runtime-switchable model
        self._last_usage = None        # populated by chat_stream_raw for cost logging
        if not CLAUDE_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
        try:
            from anthropic import Anthropic
            self._sdk = Anthropic(api_key=CLAUDE_API_KEY)
        except ImportError:
            raise ImportError("Run: pip install anthropic")

    def _active_model(self):
        from . import claude_runtime
        return self._explicit_model or claude_runtime.get_model()

    def _reasoning_kwargs(self):
        """Adaptive thinking + effort, read live from the runtime state."""
        from . import claude_runtime
        return {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": claude_runtime.get_effort()},
        }

    # ── prompt caching ────────────────────────────────────────────
    # Cache the stable prefix so repeated input bills at ~0.1x. The system
    # breakpoint caches tools + system together (tools render before system);
    # the message breakpoint caches the growing agent history.
    @staticmethod
    def _cached_system(system):
        if not PROMPT_CACHE or not system:
            return system
        return [{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}]

    @staticmethod
    def _cache_history(messages):
        """Put ONE breakpoint on the last message's last block, stripping any
        earlier ones so long agent loops never exceed the 4-breakpoint cap."""
        if not PROMPT_CACHE or not messages:
            return messages
        for m in messages:
            content = m.get("content")
            if isinstance(content, list):
                for blk in content:
                    if isinstance(blk, dict):
                        blk.pop("cache_control", None)
        last = messages[-1]
        content = last.get("content")
        if isinstance(content, str):
            last["content"] = [{"type": "text", "text": content,
                                "cache_control": {"type": "ephemeral"}}]
        elif isinstance(content, list) and content and isinstance(content[-1], dict):
            content[-1]["cache_control"] = {"type": "ephemeral"}
        return messages

    def chat(self, messages, system="", print_output=True):
        sys_prompt = system or "You are AXIO, a precise and expert AI assistant."
        for attempt in range(RETRY_ATTEMPTS):
            try:
                resp = self._sdk.messages.create(
                    model=self._active_model(), max_tokens=CLAUDE_MAX_TOKENS,
                    system=self._cached_system(sys_prompt), messages=messages,
                    **self._reasoning_kwargs(),
                )
                # With adaptive thinking, content may start with a thinking block --
                # pick the text block rather than assuming content[0].
                text = next(
                    (b.text for b in resp.content if getattr(b, "type", "") == "text"),
                    "",
                )
                if print_output:
                    print(text)
                return text
            except Exception as e:
                estr = str(e)
                if ("429" in estr or "rate_limit" in estr) and attempt < RETRY_ATTEMPTS - 1:
                    wait = 65 * (attempt + 1)
                    print(f"\n\033[33m  Rate limit - waiting {wait}s...\033[0m")
                    time.sleep(wait)
                elif attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)
                else:
                    print(f"\n\033[31m  Claude API error: {e}\033[0m")
                    return ""
        return ""

    def tool_call(self, messages, tools, system=""):
        """Tool-calling request. Returns Anthropic response object."""
        self._cache_history(messages)
        cached_system = self._cached_system(system)
        for attempt in range(RETRY_ATTEMPTS):
            try:
                return self._sdk.messages.create(
                    model=self._active_model(), max_tokens=CLAUDE_MAX_TOKENS,
                    system=cached_system, tools=tools, messages=messages,
                    **self._reasoning_kwargs(),
                )
            except Exception as e:
                estr = str(e)
                if ("429" in estr or "rate_limit" in estr) and attempt < RETRY_ATTEMPTS - 1:
                    wait = 65 * (attempt + 1)
                    print(f"\n\033[33m  Rate limit - waiting {wait}s...\033[0m")
                    time.sleep(wait)
                elif attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)
                else:
                    raise
        return None

    def chat_stream_raw(self, messages, system=""):
        """Streaming via raw Anthropic SSE API. Prints tokens live."""
        import requests as _req
        headers = {
            "x-api-key":         CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
        from . import claude_runtime
        payload = {
            "model":      self._active_model(),
            "max_tokens": CLAUDE_MAX_TOKENS,
            "system":     self._cached_system(
                              system or "You are AXIO, a precise and expert AI assistant."),
            "messages":   messages,
            "stream":     True,
            "thinking":       {"type": "adaptive"},
            "output_config":  {"effort": claude_runtime.get_effort()},
        }
        start = time.time()
        r = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=payload, stream=True, timeout=120,
        )
        if r.status_code != 200:
            print(f"\033[31m  Claude API error {r.status_code}\033[0m")
            return ""
        full = ""
        self._last_usage = None
        print(f"\n\033[35m[{self._active_model()}]\033[0m ", end="", flush=True)
        for line in r.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8") if isinstance(line, bytes) else line
            if line.startswith("data:"):
                ds = line[5:].strip()
                if ds == "[DONE]":
                    break
                try:
                    event = json.loads(ds)
                    etype = event.get("type")
                    if etype == "message_start":
                        u = event.get("message", {}).get("usage", {}) or {}
                        self._last_usage = {
                            "input_tokens":                u.get("input_tokens", 0),
                            "cache_read_input_tokens":     u.get("cache_read_input_tokens", 0),
                            "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0),
                            "output_tokens":               u.get("output_tokens", 0),
                        }
                    elif etype == "content_block_delta":
                        token = event.get("delta", {}).get("text", "")
                        print(token, end="", flush=True)
                        full += token
                    elif etype == "message_delta":
                        u = event.get("usage", {}) or {}
                        if self._last_usage is not None and "output_tokens" in u:
                            self._last_usage["output_tokens"] = u["output_tokens"]
                except json.JSONDecodeError:
                    pass
        elapsed = round(time.time() - start, 2)
        print(f"\n\033[90m[{elapsed}s | Claude]\033[0m")
        return full


# ─────────────────────────────────────────────────────────
#  MODEL ROUTER  (thin wrapper around core.router)
# ─────────────────────────────────────────────────────────

class ModelRouter:
    """
    Keyword-based routing. Delegates to core.router so the logic lives in a
    fresh module with no stale bytecode cache issues.
    """

    @classmethod
    def detect(cls, prompt):
        from .router import detect as _detect
        return _detect(prompt)

    @classmethod
    def needs_claude(cls, prompt):
        from .router import needs_claude as _nc
        return _nc(prompt)
