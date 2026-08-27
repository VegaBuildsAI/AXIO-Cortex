"""
benchmark_models.py — AXIO v2.1 benchmark runner
Runs all test prompts against each Ollama model and logs results to
axio-console-v2.1/logs/model_tests.jsonl.

Routing:
  MATH-001  → exact_math route (Python tool, no Ollama call)
  All others → Ollama via /api/generate

Usage:
  python scripts/benchmark_models.py              # run all models, all tests
  python scripts/benchmark_models.py --model gemma4:12b   # single model
  python scripts/benchmark_models.py --test MATH-001     # single test
"""

import json
import sys
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
ENGINE_DIR  = PROJECT_DIR / "engine"
OUT         = PROJECT_DIR / "logs" / "model_tests.jsonl"
OUT.parent.mkdir(parents=True, exist_ok=True)

# Add engine dir to path so math_tool is importable
sys.path.insert(0, str(ENGINE_DIR))

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# ── Models ─────────────────────────────────────────────────────────────────────
MODELS = [
    "gemma4:12b",
    "qwen3.6:latest",
]

# ── Tests ──────────────────────────────────────────────────────────────────────
TESTS = [
    {
        "id":       "MATH-001",
        "prompt":   "Calculate exactly: 84736291 * 69384725. Return only FINAL_RESULT.",
        "expected": "5879404248554975",  # verified: 84736291 * 69384725 (Python-computed)
        "type":     "math",
        "route":    "exact_math",   # → Python tool, not Ollama
    },
    {
        "id":     "CODING-001",
        "prompt": "Write a FastAPI endpoint /health that returns status ok with production-ready structure.",
        "type":   "coding",
        "route":  "coding_agent",
    },
    {
        "id":     "REVREC-001",
        "prompt": "Create an ASC 606 decision tree for identifying performance obligations in a SaaS contract.",
        "type":   "revenue",
        "route":  "revenue_analysis",
    },
    {
        "id":     "ARCH-001",
        "prompt": "Design a local AI orchestration architecture using Ollama, Python tools, YAML config, and audit logs.",
        "type":   "architecture",
        "route":  "coding_agent",
    },
]

# ── Ollama caller ──────────────────────────────────────────────────────────────
def call_ollama(model: str, prompt: str, num_ctx: int = 4096, num_predict: int = 1024) -> dict:
    payload = {
        "model":  model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p":       0.8,
            "num_ctx":     num_ctx,
            "num_predict": num_predict,
        },
    }
    start    = time.time()
    response = requests.post(OLLAMA_URL, json=payload, timeout=600)
    elapsed  = round(time.time() - start, 2)
    response.raise_for_status()
    data = response.json()
    return {
        "model":           model,
        "elapsed_seconds": elapsed,
        "response":        data.get("response", ""),
    }


# ── Math scorer (fallback for Ollama-generated math responses) ─────────────────
def score_math_response(response: str, expected: str) -> int:
    clean = response.replace(",", "").replace(" ", "")
    return 100 if expected in clean else 0


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    # Optional filters from CLI
    target_models = MODELS[:]
    target_tests  = [t["id"] for t in TESTS]

    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        target_models = [sys.argv[idx + 1]]

    if "--test" in sys.argv:
        idx = sys.argv.index("--test")
        target_tests = [sys.argv[idx + 1]]

    # Context caps per route (avoid Ollama OOM/timeout)
    CTX = {
        "coding_agent":    8192,
        "revenue_analysis": 8192,
        "quick_chat":       4096,
        "exact_math":          0,   # not used — Python handles this
    }
    PREDICT = 1024

    results = []

    # Load math_tool once
    try:
        from math_tool import solve as math_solve
        math_tool_available = True
    except ImportError:
        print("[warn] math_tool not found — math tests will fall back to Ollama.")
        math_tool_available = False

    for test in TESTS:
        if test["id"] not in target_tests:
            continue

        route = test.get("route", "coding_agent")

        # ── exact_math route: Python tool, one shared result for all models ──
        if route == "exact_math" and math_tool_available:
            print(f"\n[Python tool] {test['id']} — using exact_math route (no Ollama)")
            solution = math_solve(test["prompt"])
            ts = datetime.now(timezone.utc).isoformat()

            # Log one entry tagged model="python_exact" — shared ground truth
            row = {
                "model":           "python_exact",
                "test_id":          test["id"],
                "test_type":        test["type"],
                "route":            "exact_math",
                "ts":               ts,
                "elapsed_seconds":  0.0,
                "response":         solution.get("result", ""),
                "score":            solution["score"],
                "score_label":      "Excellent" if solution["score"] == 100 else "Fail",
                "score_reasoning":  f"Python computed: {solution.get('expression')} = {solution.get('result')}",
                "scored_at":        ts,
                "scored_by":        "python_exact",
                "method":           "python_exact",
            }
            if solution.get("error"):
                row["error"] = solution["error"]

            results.append(row)
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

            print(f"  Result: {solution.get('result')}  Score: {solution['score']}/100")
            # Skip sending to individual Ollama models for this test
            continue

        # ── All other routes: call Ollama per model ──
        num_ctx = CTX.get(route, 4096)

        for model in target_models:
            print(f"Running {test['id']} on {model}  (ctx={num_ctx})...")
            try:
                result  = call_ollama(model, test["prompt"], num_ctx=num_ctx, num_predict=PREDICT)
                score   = None
                if test["type"] == "math":
                    score = score_math_response(result["response"], test.get("expected", ""))
                row = {
                    "model":           model,
                    "test_id":          test["id"],
                    "test_type":        test["type"],
                    "route":            route,
                    "ts":               datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds":  result["elapsed_seconds"],
                    "response":         result["response"],
                    "score":            score,
                }
            except Exception as exc:
                row = {
                    "model":     model,
                    "test_id":    test["id"],
                    "test_type":  test["type"],
                    "route":      route,
                    "ts":         datetime.now(timezone.utc).isoformat(),
                    "error":      str(exc),
                }

            results.append(row)
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nBenchmark complete. Results saved to: {OUT}")
    print(f"Total runs: {len(results)}")


if __name__ == "__main__":
    main()
