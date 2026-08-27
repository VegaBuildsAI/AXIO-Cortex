"""
AXIO Core Configuration
Central source of truth for paths, model names, API endpoints, and routing rules.
All environment variables are loaded from .env (ANTHROPIC_API_KEY, CLAUDE_MODEL, etc.)
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------
#  PATHS
# ---------------------------------------------------------
BASE         = Path(__file__).resolve().parent.parent
AXIO_DATA_ROOT = Path(
    os.getenv("AXIO_DATA_ROOT", str(Path.home() / ".axio"))
).expanduser().resolve()
LOG_DIR      = BASE / "logs"
SESSIONS_DIR = AXIO_DATA_ROOT / "sessions"
MEMORY_DIR   = AXIO_DATA_ROOT / "memory"   # structured JSON facts per mode
CHROMA_DIR   = AXIO_DATA_ROOT / "chroma-resilient"  # exact Postgres mirror (RAG fallback)
JOURNAL_DIR  = AXIO_DATA_ROOT / "journals" # crash-safe live session snapshots
OUTBOX_DIR   = AXIO_DATA_ROOT / "outbox"   # durable Postgres replay queue
OUTPUT_DIR   = BASE / "workspaces"
PROMPTS_DIR  = BASE / "prompts"
CONFIG_DIR   = BASE / "config"
CODE_SKILLS_ROOT = Path(
    os.getenv("AXIO_CODE_SKILLS_ROOT", str(BASE / "skills"))
).expanduser().resolve()
CODE_TEMPLATES_DIR = Path(
    os.getenv("AXIO_CODE_TEMPLATES_DIR", str(BASE / "templates" / "code"))
).expanduser().resolve()

# ---------------------------------------------------------
#  OLLAMA
# ---------------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_CHAT = f"{OLLAMA_HOST}/api/chat"
OLLAMA_GEN  = f"{OLLAMA_HOST}/api/generate"
OLLAMA_TAGS = f"{OLLAMA_HOST}/api/tags"
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "8192"))

# Local models by role -- override with env vars (.env MODEL_* wins).
# HYBRID SCHEME: gemma4:12b is the local base; the agentic tier (code / reasoning
# / revenue / complex) boosts to the Claude API (see CLAUDE_MODEL below). The
# `coding`/`reasoning` tags here are the LOCAL fallback used only when Claude is
# unavailable or LOCAL_ONLY=1 -- gemma4:12b, since this machine can't run a 24GB
# model. Everything light (chat, fast, vision) stays on gemma4:12b.
MODELS = {
    "chat":      os.getenv("MODEL_CHAT",      "gemma4:12b"),
    "coding":    os.getenv("MODEL_CODING",    "gemma4:12b"),
    "reasoning": os.getenv("MODEL_REASONING", "gemma4:12b"),
    "fast":      os.getenv("MODEL_FAST",      "gemma4:12b"),
    "fallback":  os.getenv("MODEL_FALLBACK",  "gemma4:12b"),
    "vision":    os.getenv("MODEL_VISION",    "gemma4:12b"),
}

# Deterministic mode routing for the local UI. Chat + Cowork run on the local
# model; Code boosts to the Claude API (the frontier agentic tier). Set
# LOCAL_ONLY=1 to force every mode on-device (Code then uses the local fallback).
MODE_BACKENDS = {
    "chat": "ollama",
    "cowork": "ollama",
    "code": "claude",
}

# ---------------------------------------------------------
#  CLAUDE (CLOUD)
# ---------------------------------------------------------
CLAUDE_API_KEY    = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")

# Selectable Claude presets for in-app switching (short alias -> model id).
# Switch at runtime in a mode with e.g.  model opus max  /  model sonnet high.
CLAUDE_MODELS = {
    "sonnet": "claude-sonnet-4-6",   # lighter / cheaper Claude tier
    "opus":   "claude-opus-4-8",     # frontier agentic tier
}
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")  # active default (cheaper)
CLAUDE_MODEL_CHAT = os.getenv("CLAUDE_MODEL_CHAT", "claude-haiku-4-5-20251001")
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "16000"))   # room for thinking + output

# Effort for the Claude tier. Wired into ClaudeClient via output_config.effort
# + adaptive thinking. NOTE: xhigh is Opus-only; Sonnet 4.6 accepts low/medium/high/max.
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
CLAUDE_EFFORT  = os.getenv("CLAUDE_EFFORT", "high").strip().lower()
if CLAUDE_EFFORT not in CLAUDE_EFFORTS:
    CLAUDE_EFFORT = "high"

# Prompt caching: cache the stable prefix (system + tools, and the growing agent
# history) so repeated input bills at ~0.1x. Set PROMPT_CACHE=0 to disable.
PROMPT_CACHE = os.getenv("PROMPT_CACHE", "1").strip() not in ("0", "false", "no", "")

# LOCAL_ONLY=1 deactivates the cloud path entirely: the router sends premium
# routes to a local model, --claude/FORCE_CLAUDE is ignored, and Code mode runs
# the local agent instead of Claude. Default 0 = hybrid (local base + Claude boost).
LOCAL_ONLY = os.getenv("LOCAL_ONLY", "").strip() in ("1", "true", "yes")

# ---------------------------------------------------------
#  LIMITS
# ---------------------------------------------------------
# Legacy web_api service-loop cap. Interactive Code and RevRec use the adaptive
# 10/20/50/100 budgets from core.code_tools.router instead.
MAX_ITERS      = 20
MAX_FILE_BYTES = 200_000
MAX_FILE_CHARS = 8_000
CONTEXT_LIMIT  = int(os.getenv("CONTEXT_MESSAGE_LIMIT", "50"))
RETRY_ATTEMPTS = 3
RETRY_BACKOFF  = 2        # exponential backoff multiplier
TIMEOUT        = 600      # seconds per model request
CODE_SKILL_MAX_CHARS = int(os.getenv("AXIO_CODE_SKILL_MAX_CHARS", "24000"))
# Shared multiline console budget for Chat, Cowork, and Code.  The older
# Code-only variable remains a supported fallback so existing .env files keep
# their behavior while all three modes use one source of truth.
INPUT_MAX_CHARS = int(
    os.getenv(
        "AXIO_INPUT_MAX_CHARS",
        os.getenv("AXIO_CODE_INPUT_MAX_CHARS", "60000"),
    )
)
CODE_INPUT_MAX_CHARS = INPUT_MAX_CHARS  # backward-compatible public alias
CODE_PYTHON_TIMEOUT  = int(os.getenv("AXIO_CODE_PYTHON_TIMEOUT", "120"))
CODE_NODE_TIMEOUT    = int(os.getenv("AXIO_CODE_NODE_TIMEOUT", "300"))
CODE_TOOL_ROUTING_MODE = os.getenv("AXIO_CODE_TOOL_ROUTING_MODE", "full").strip().lower()
if CODE_TOOL_ROUTING_MODE not in {"full", "dynamic"}:
    CODE_TOOL_ROUTING_MODE = "full"
CODE_COMMAND_TIMEOUT = int(os.getenv("AXIO_CODE_COMMAND_TIMEOUT", "120"))

# ---------------------------------------------------------
#  CODE WEB / BROWSER / RETRIEVAL
# ---------------------------------------------------------
AXIO_SEARXNG_URL = os.getenv("AXIO_SEARXNG_URL", "http://127.0.0.1:8080").rstrip("/")
AXIO_WEB_TIMEOUT = int(os.getenv("AXIO_WEB_TIMEOUT", "20"))
AXIO_WEB_MAX_BYTES = int(os.getenv("AXIO_WEB_MAX_BYTES", "2000000"))
AXIO_WEB_MAX_CHARS = int(os.getenv("AXIO_WEB_MAX_CHARS", "24000"))
AXIO_BROWSER_TIMEOUT = int(os.getenv("AXIO_BROWSER_TIMEOUT", "20"))
AXIO_CODE_KNOWLEDGE_DIR = Path(
    os.getenv("AXIO_CODE_KNOWLEDGE_DIR", str(AXIO_DATA_ROOT / "knowledge"))
).expanduser().resolve()
AXIO_WORKSPACE_INDEX_DB = AXIO_CODE_KNOWLEDGE_DIR / "workspace.db"
AXIO_DOCS_INDEX_DB = AXIO_CODE_KNOWLEDGE_DIR / "docs.db"
AXIO_WEB_CACHE_DB = AXIO_CODE_KNOWLEDGE_DIR / "web_cache.db"
AXIO_RETRIEVAL_MAX_FILES = int(os.getenv("AXIO_RETRIEVAL_MAX_FILES", "300"))
AXIO_RETRIEVAL_MAX_CHUNKS = int(os.getenv("AXIO_RETRIEVAL_MAX_CHUNKS", "2000"))

# ---------------------------------------------------------
#  MEMORY
# ---------------------------------------------------------
MEMORY_RECALL_RESULTS = int(os.getenv("MEMORY_RECALL_RESULTS", "5"))
MEMORY_SUMMARIZE      = os.getenv("MEMORY_SUMMARIZE", "1") in ("1", "true", "yes")
MEMORY_SUMMARY_MODEL  = os.getenv("MEMORY_SUMMARY_MODEL", "gemma4:12b")
# EMBEDDING MODEL -- do NOT change. This is the background tokenizer that powers
# Tier-2 memory / RAG (768-dim). The Postgres backend hard-asserts dim==768, so
# swapping it would break the vector store. It is separate from the generation
# models above and is never routed through MODELS / the chat endpoints.
MEMORY_EMBED_MODEL    = os.getenv("MEMORY_EMBED_MODEL",   "nomic-embed-text:latest")

# ---------------------------------------------------------
#  LIVE DATABASE BACKEND
# ---------------------------------------------------------
AXIO_MEMORY_BACKEND = os.getenv("AXIO_MEMORY_BACKEND", "json").strip().lower() or "json"

AXIO_DB_HOST     = os.getenv("AXIO_DB_HOST", "127.0.0.1")
AXIO_DB_PORT     = int(os.getenv("AXIO_DB_PORT", "5432"))
AXIO_DB_NAME     = os.getenv("AXIO_DB_NAME", "axio_cortex")
AXIO_DB_USER     = os.getenv("AXIO_DB_USER", "axio")
AXIO_DB_PASSWORD = os.getenv("AXIO_DB_PASSWORD", "local-dev-password")

# ---------------------------------------------------------
#  SMART ROUTING -- keyword -> route
#  Premium is checked FIRST so it wins over revenue for PDF/legal/audit tasks.
#  The router also runs an arithmetic-expression regex for math detection.
# ---------------------------------------------------------
ROUTE_KEYWORDS = {
    "premium": [
        "pdf", ".pdf", "legal document", "legal memo", "legal",
        "large codebase", "complex architecture", "production bug",
        "high-value deliverable", "asc606 policy memo", "audit memo",
        "client deliverable", "deep analysis", "production ready",
        "contract modification", "large contract", "full analysis",
        "complex legal", "compliance", "enterprise",
    ],
    "coding": [
        "python", "fastapi", "script", "code", "function", "class", "bug",
        "refactor", "api", "endpoint", "import", "debug", "error", "fix",
        "repository", "repo", "module", "def ", "async", "sql", "database",
        "write a", "build a", "implement", "add a", "create a script",
        "unit test", "unit tests", "test suite", "tests",
    ],
    "revenue": [
        "asc 606", "asc606", "ifrs", "revenue recognition", "performance obligation",
        "variable consideration", "contract", "saas revenue", "deferred",
        "standalone selling price", "ssp", "allocation", "constraint", "ifrs 15",
        "excel", "spreadsheet", "excel model", "financial model",
    ],
    "math": [
        "calculate", "compute", "multiply", "divide", "sum of",
        "integral", "derivative", "equation", "solve for", "exact result",
        "arithmetic",
    ],
}

# File extensions the cowork workspace agent will index
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".md", ".txt", ".sql", ".sh", ".ps1", ".env.example",
    ".csv", ".xml", ".rs", ".go", ".java", ".c", ".cpp", ".h",
}
