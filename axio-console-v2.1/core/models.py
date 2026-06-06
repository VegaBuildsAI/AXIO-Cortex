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
    CLAUDE_API_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS,
    RETRY_ATTEMPTS, RETRY_BACKOFF, TIMEOUT,
)


# ─────────────────────────────────────────────────────────
#  OLLAMA CLIENT
# ─────────────────────────────────────────────────────────

class OllamaClient:
    """Connects to a local Ollama instance with retry logic."""

    def __init__(self, host=None):
        self.host = (host or OLLAMA_HOST).rstrip("/")
        self._thinking_cache = {}

    def _supports_thinking(self, model):
        """True if the model advertises the 'thinking' capability (qwen3 dense).

        Cached per model. Used to send think:false so thinking tokens don't
        consume the output budget / slow responses (ASSESS-004). Non-thinking
        models (mistral, llama3.1, qwen3-coder) are left untouched.
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
        payload = {"model": model, "messages": messages, "stream": True}
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
            "options": options or {"temperature": 0.2, "top_p": 0.85},
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
                    break
        elapsed = round(time.time() - start, 2)
        print(f"\n\033[90m[{elapsed}s]\033[0m")
        return full, elapsed

    def tool_call(self, model, messages, tools):
        """Send a tool-calling request to Ollama (non-streaming)."""
        payload = {"model": model, "messages": messages,
                   "tools": tools, "stream": False}
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
                return r.json()
            except requests.exceptions.ReadTimeout:
                if attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)
                else:
                    raise
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
    """Wraps the Anthropic SDK for chat and tool-calling."""

    def __init__(self, model: str = None):
        self._model = model or CLAUDE_MODEL
        if not CLAUDE_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
        try:
            from anthropic import Anthropic
            self._sdk = Anthropic(api_key=CLAUDE_API_KEY)
        except ImportError:
            raise ImportError("Run: pip install anthropic")

    def chat(self, messages, system="", print_output=True):
        sys_prompt = system or "You are AXIO, a precise and expert AI assistant."
        for attempt in range(RETRY_ATTEMPTS):
            try:
                resp = self._sdk.messages.create(
                    model=self._model, max_tokens=CLAUDE_MAX_TOKENS,
                    system=sys_prompt, messages=messages,
                )
                text = resp.content[0].text if resp.content else ""
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
        for attempt in range(RETRY_ATTEMPTS):
            try:
                return self._sdk.messages.create(
                    model=self._model, max_tokens=CLAUDE_MAX_TOKENS,
                    system=system, tools=tools, messages=messages,
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
        payload = {
            "model":      self._model,
            "max_tokens": CLAUDE_MAX_TOKENS,
            "system":     system or "You are AXIO, a precise and expert AI assistant.",
            "messages":   messages,
            "stream":     True,
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
        print(f"\n\033[35m[{self._model}]\033[0m ", end="", flush=True)
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
                    if event.get("type") == "content_block_delta":
                        token = event.get("delta", {}).get("text", "")
                        print(token, end="", flush=True)
                        full += token
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
