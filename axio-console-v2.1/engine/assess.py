"""
AXIO Improvement Engine — Assessment Runner
Reads all audit logs, scores unscored benchmarks, and appends
one snapshot to engine/assessments.jsonl.

Run manually:  python engine/assess.py
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

# Ensure project root is on path so scorer import works
ENGINE_DIR  = Path(__file__).parent
PROJECT_DIR = ENGINE_DIR.parent
LOGS_DIR    = PROJECT_DIR / "logs"
ASSESSMENTS = ENGINE_DIR / "assessments.jsonl"

LOG_FILES = {
    "console":   LOGS_DIR / "console_audit.jsonl",
    "code":      LOGS_DIR / "code_audit.jsonl",
    "agent":     LOGS_DIR / "agent_audit.jsonl",
    "rev_agent": LOGS_DIR / "rev_agent_audit.jsonl",
    "chat":      LOGS_DIR / "chat_audit.jsonl",
    "model_tests": LOGS_DIR / "model_tests.jsonl",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def assessment_id() -> str:
    existing = load_jsonl(ASSESSMENTS)
    return f"ASSESS-{len(existing) + 1:03d}"


def safe_avg(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


# ── Log readers ────────────────────────────────────────────────────────────────

def read_console_audit() -> dict:
    entries = load_jsonl(LOG_FILES["console"])
    routes  = defaultdict(lambda: {"count": 0, "latencies": [], "models": set()})

    for e in entries:
        route = e.get("route") or "unknown"
        routes[route]["count"] += 1
        if e.get("elapsed_seconds") is not None:
            routes[route]["latencies"].append(e["elapsed_seconds"])
        if e.get("model"):
            routes[route]["models"].add(e["model"])

    result = {}
    for route, data in routes.items():
        result[route] = {
            "count":         data["count"],
            "avg_latency_s": safe_avg(data["latencies"]),
            "models_used":   sorted(data["models"]),
        }
    return result


def read_tool_audit(log_key: str) -> dict:
    """Generic reader for agent/code/rev_agent audit logs."""
    entries  = load_jsonl(LOG_FILES[log_key])
    by_model = defaultdict(lambda: {"tool_calls": 0, "tasks": set(), "errors": 0})

    for e in entries:
        model = e.get("model") or "unknown"
        by_model[model]["tool_calls"] += 1
        if e.get("task_preview"):
            by_model[model]["tasks"].add(e["task_preview"][:60])
        result = e.get("result_preview", "")
        if result and ("error" in result.lower() or "exception" in result.lower()):
            by_model[model]["errors"] += 1

    return {
        model: {
            "tool_calls":  data["tool_calls"],
            "unique_tasks": len(data["tasks"]),
            "errors":       data["errors"],
        }
        for model, data in by_model.items()
    }


def read_chat_audit() -> dict:
    entries  = load_jsonl(LOG_FILES["chat"])
    sessions = [e for e in entries if e.get("event") == "session_start"]
    return {
        "total_sessions":  len(sessions),
        "total_events":    len(entries),
    }


def read_model_tests() -> dict:
    entries  = load_jsonl(LOG_FILES["model_tests"])
    by_model = defaultdict(lambda: {
        "scores": defaultdict(list),
        "errors": 0,
        "scored": 0,
        "pending": 0,
    })

    for e in entries:
        model     = e.get("model", "unknown")
        test_type = e.get("test_type", "unknown")

        if e.get("error"):
            by_model[model]["errors"] += 1
            continue

        score = e.get("score")
        if score is not None:
            by_model[model]["scores"][test_type].append(score)
            by_model[model]["scored"] += 1
        elif e.get("response"):
            by_model[model]["pending"] += 1

    result = {}
    for model, data in by_model.items():
        result[model] = {
            "benchmark_scores": {
                t: safe_avg(scores)
                for t, scores in data["scores"].items()
            },
            "scored_responses": data["scored"],
            "pending_responses": data["pending"],
            "timeout_errors":   data["errors"],
        }
    return result


# ── Delta calculation ──────────────────────────────────────────────────────────

def compute_delta(current: dict, previous: dict | None) -> dict:
    """Compare benchmark scores to prior assessment."""
    if not previous:
        return {}
    prev_models = previous.get("by_model", {})
    deltas = {}
    for model, data in current.items():
        prev = prev_models.get(model, {}).get("benchmark_scores", {})
        curr = data.get("benchmark_scores", {})
        model_delta = {}
        for test_type, score in curr.items():
            if score is not None and prev.get(test_type) is not None:
                model_delta[test_type] = round(score - prev[test_type], 1)
            else:
                model_delta[test_type] = None
        if model_delta:
            deltas[model] = model_delta
    return deltas


# ── Health flags ───────────────────────────────────────────────────────────────

def build_health_flags(model_tests: dict, route_data: dict) -> list[dict]:
    flags = []

    for model, data in model_tests.items():
        if data["timeout_errors"] > 0:
            flags.append({
                "severity": "warn",
                "model":    model,
                "issue":    f"{data['timeout_errors']} benchmark timeout(s)",
            })
        if data["pending_responses"] > 0:
            flags.append({
                "severity": "info",
                "model":    model,
                "issue":    f"{data['pending_responses']} response(s) awaiting scoring",
            })

    total_pending = sum(d["pending_responses"] for d in model_tests.values())
    if total_pending > 0:
        flags.append({
            "severity": "info",
            "model":    "all",
            "issue":    f"{total_pending} benchmark response(s) scored this run",
        })

    return flags


# ── Main ───────────────────────────────────────────────────────────────────────

def run_assessment() -> dict:
    ts_start = datetime.now(timezone.utc).isoformat()
    print(f"\n{'='*60}")
    print(f"  AXIO Assessment Runner")
    print(f"  {ts_start}")
    print(f"{'='*60}\n")

    # Step 1: Score any unscored benchmarks first
    print("[assess] Step 1/5 — Running scorer on unscored benchmarks...")
    try:
        sys.path.insert(0, str(ENGINE_DIR))
        from scorer import run_scorer
        model_entries = run_scorer(verbose=True)
    except Exception as e:
        print(f"[assess] Scorer failed: {e} — continuing without scoring.")

    # Step 2: Read all logs
    print("\n[assess] Step 2/5 — Reading audit logs...")
    console_data  = read_console_audit()
    code_data     = read_tool_audit("code")
    agent_data    = read_tool_audit("agent")
    rev_data      = read_tool_audit("rev_agent")
    chat_data     = read_chat_audit()
    benchmark_data = read_model_tests()

    # Step 3: Merge tool call data by model
    print("[assess] Step 3/5 — Aggregating model activity...")
    all_models = set()
    all_models.update(benchmark_data.keys())
    all_models.update(code_data.keys())
    all_models.update(agent_data.keys())
    all_models.update(rev_data.keys())
    for route in console_data.values():
        all_models.update(route.get("models_used", []))

    by_model = {}
    for model in sorted(all_models):
        bm = benchmark_data.get(model, {})
        tool_calls = (
            code_data.get(model, {}).get("tool_calls", 0) +
            agent_data.get(model, {}).get("tool_calls", 0) +
            rev_data.get(model, {}).get("tool_calls", 0)
        )
        routes_active = [
            route for route, rd in console_data.items()
            if model in rd.get("models_used", [])
        ]
        by_model[model] = {
            "benchmark_scores":   bm.get("benchmark_scores", {}),
            "scored_responses":   bm.get("scored_responses", 0),
            "pending_responses":  bm.get("pending_responses", 0),
            "timeout_errors":     bm.get("timeout_errors", 0),
            "tool_calls":         tool_calls,
            "routes_active":      routes_active,
        }

    # Step 4: Load previous assessment for delta
    print("[assess] Step 4/5 — Computing deltas...")
    prev_assessments = load_jsonl(ASSESSMENTS)
    previous = prev_assessments[-1] if prev_assessments else None
    delta = compute_delta(by_model, previous)

    # Step 5: Build and write snapshot
    print("[assess] Step 5/5 — Writing snapshot...")
    total_tool_calls = sum(
        m.get("tool_calls", 0) for m in by_model.values()
    )
    total_pending = sum(
        m.get("pending_responses", 0) for m in by_model.values()
    )
    total_scored = sum(
        m.get("scored_responses", 0) for m in by_model.values()
    )
    total_errors = sum(
        m.get("timeout_errors", 0) for m in by_model.values()
    )
    total_entries = sum(
        len(load_jsonl(p)) for p in LOG_FILES.values() if p.exists()
    )

    snapshot = {
        "assessment_id": assessment_id(),
        "ts":            ts_start,
        "summary": {
            "total_log_entries":    total_entries,
            "active_models":        sorted(all_models - {"unknown"}),
            "total_tool_calls":     total_tool_calls,
            "total_console_queries": sum(r["count"] for r in console_data.values()),
            "chat_sessions":        chat_data["total_sessions"],
            "benchmarks_scored":    total_scored,
            "benchmarks_pending":   total_pending,
            "benchmark_errors":     total_errors,
        },
        "by_model":      by_model,
        "by_route":      console_data,
        "benchmark_delta": delta,
        "health_flags":  build_health_flags(benchmark_data, console_data),
    }

    ASSESSMENTS.parent.mkdir(parents=True, exist_ok=True)
    with open(ASSESSMENTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot) + "\n")

    print(f"\n{'='*60}")
    print(f"  Assessment {snapshot['assessment_id']} complete.")
    print(f"  Models tracked : {len(by_model)}")
    print(f"  Tool calls     : {total_tool_calls}")
    print(f"  Benchmarks     : {total_scored} scored / {total_pending} pending")
    print(f"  Health flags   : {len(snapshot['health_flags'])}")
    print(f"  Saved to       : {ASSESSMENTS}")
    print(f"{'='*60}\n")

    return snapshot


if __name__ == "__main__":
    run_assessment()
