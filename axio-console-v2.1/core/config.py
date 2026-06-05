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
LOG_DIR      = BASE / "logs"
SESSIONS_DIR = Path.home() / ".axio" / "sessions"
MEMORY_DIR   = Path.home() / ".axio" / "memory"   # structured JSON facts per mode
CHROMA_DIR   = Path.home() / ".axio" / "chroma"   # ChromaDB vector store (RAG)
OUTPUT_DIR   = BASE / "workspaces"
PROMPTS_DIR  = BASE / "prompts"
CONFIG_DIR   = BASE / "config"

# ---------------------------------------------------------
#  OLLAMA
# ---------------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_CHAT = f"{OLLAMA_HOST}/api/chat"
OLLAMA_GEN  = f"{OLLAMA_HOST}/api/generate"
OLLAMA_TAGS = f"{OLLAMA_HOST}/api/tags"

# Local models by role -- override with env vars
MODELS = {
    "chat":      os.getenv("MODEL_CHAT",      "mistral:latest"),
    "coding":    os.getenv("MODEL_CODING",    "qwen3-coder:30b"),
    "reasoning": os.getenv("MODEL_REASONING", "qwen3:14b"),
    "fast":      os.getenv("MODEL_FAST",      "qwen3:8b"),
    "fallback":  os.getenv("MODEL_FALLBACK",  "qwen3:8b"),
}

# ---------------------------------------------------------
#  CLAUDE (CLOUD)
# ---------------------------------------------------------
CLAUDE_API_KEY    = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_MODEL_CHAT = os.getenv("CLAUDE_MODEL_CHAT", "claude-haiku-4-5-20251001")
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "4096"))

# ---------------------------------------------------------
#  LIMITS
# ---------------------------------------------------------
MAX_ITERS      = 20
MAX_FILE_BYTES = 80_000
MAX_FILE_CHARS = 8_000
CONTEXT_LIMIT  = 50       # max messages before session pruning
RETRY_ATTEMPTS = 3
RETRY_BACKOFF  = 2        # exponential backoff multiplier
TIMEOUT        = 600      # seconds per model request

# ---------------------------------------------------------
#  MEMORY
# ---------------------------------------------------------
MEMORY_RECALL_RESULTS = int(os.getenv("MEMORY_RECALL_RESULTS", "5"))
MEMORY_SUMMARIZE      = os.getenv("MEMORY_SUMMARIZE", "1") in ("1", "true", "yes")
MEMORY_SUMMARY_MODEL  = os.getenv("MEMORY_SUMMARY_MODEL", "qwen3:14b")
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
