r"""A/B benchmark for AXIO's 38-tool baseline versus the dynamic tool router.

The benchmark asks the local model to select exactly one first tool. It never
executes the selected tool, so write, execute, destructive, and external actions
remain inert. Results use Ollama's real prompt_eval_count rather than the
trajectory logger's character-based token estimate.

Usage:
    .\.venv\Scripts\python.exe scripts\benchmark_tool_router.py
    .\.venv\Scripts\python.exe scripts\benchmark_tool_router.py --repeats 3
    .\.venv\Scripts\python.exe scripts\benchmark_tool_router.py --task RS-01
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core.code_tools import build_default_registry  # noqa: E402
from core.code_tools.router import DynamicToolRouter, TaskType  # noqa: E402
from core.config import OLLAMA_HOST  # noqa: E402


SYSTEM_PROMPT = """You are an AXIO tool-selection evaluator.
Choose exactly one best FIRST tool for the user task and call it now.
Do not execute the task yourself, do not narrate, and do not invent a result.
If the needed registered capability is not visible, call request_tool with its
exact registered name and a concise reason. Never call more than one tool."""


@dataclass(frozen=True)
class BenchmarkTask:
    id: str
    task_type: TaskType
    prompt: str
    baseline_expected: tuple[str, ...]
    router_expected: tuple[str, ...]
    request_target: str = ""


TASKS = (
    BenchmarkTask(
        "CE-01", TaskType.CODE_EDIT,
        "Create a new UTF-8 Python file at C:\\benchmark\\hello.py containing print('hello').",
        ("write_file",), ("write_file",),
    ),
    BenchmarkTask(
        "CE-02", TaskType.CODE_EDIT,
        "Implement a code edit by replacing one exact unique occurrence in C:\\benchmark\\app.py.",
        ("edit_file",), ("edit_file",),
    ),
    BenchmarkTask(
        "CE-03", TaskType.CODE_EDIT,
        "Implement one atomic patch containing exact replacements across two existing files. "
        "Use the dedicated multi-file capability; if hidden, request it first.",
        ("apply_patch",), ("request_tool",), "apply_patch",
    ),
    BenchmarkTask(
        "DB-01", TaskType.DEBUGGING,
        "Debug a traceback by searching all Python source files for calls to parse_config before editing.",
        ("grep_files",), ("grep_files",),
    ),
    BenchmarkTask(
        "DB-02", TaskType.DEBUGGING,
        "Debug a failing Windows build by running the diagnostic PowerShell command supplied by the user.",
        ("run_command",), ("run_command",),
    ),
    BenchmarkTask(
        "DB-03", TaskType.DEBUGGING,
        "Debug a regression by inspecting the current Git diff. Use the dedicated diff capability; "
        "if it is hidden, request it first.",
        ("git_diff",), ("request_tool",), "git_diff",
    ),
    BenchmarkTask(
        "RS-01", TaskType.RESEARCH,
        "Research the latest official FastAPI release documentation on the public web.",
        ("web_search",), ("web_search",),
    ),
    BenchmarkTask(
        "RS-02", TaskType.RESEARCH,
        "Research this known public page by fetching https://fastapi.tiangolo.com/deployment/ directly.",
        ("web_fetch", "browser_open"), ("web_fetch",),
    ),
    BenchmarkTask(
        "RS-03", TaskType.RESEARCH,
        "Research a previously fetched page by extracting readable text from cache_id abc123.",
        ("web_extract",), ("web_extract",),
    ),
    BenchmarkTask(
        "PL-01", TaskType.PLANNING,
        "Audit the codebase and plan a change by finding every textual reference to MAX_ITERS.",
        ("grep_files",), ("grep_files",),
    ),
    BenchmarkTask(
        "PL-02", TaskType.PLANNING,
        "Plan a Playwright integration using the cached official library documentation before editing.",
        ("search_docs",), ("search_docs",),
    ),
    BenchmarkTask(
        "PL-03", TaskType.PLANNING,
        "Review the current unstaged code changes and plan the next implementation step.",
        ("git_diff", "git_status"), ("git_diff",),
    ),
    BenchmarkTask(
        "TS-01", TaskType.TESTING,
        "Test the existing script C:\\benchmark\\probe.py with the configured Python interpreter.",
        ("run_python",), ("run_python",),
    ),
    BenchmarkTask(
        "TS-02", TaskType.TESTING,
        "Test the Node project by running its declared npm test script with the dedicated safe tool.",
        ("run_npm_script",), ("run_npm_script",),
    ),
    BenchmarkTask(
        "TS-03", TaskType.TESTING,
        "Before testing, inspect the Python environment and installed distributions. Use the dedicated "
        "environment capability; if hidden, request it first.",
        ("inspect_python_environment",), ("request_tool",), "inspect_python_environment",
    ),
    BenchmarkTask(
        "FO-01", TaskType.FILE_OPS,
        "List the bounded contents of C:\\benchmark without modifying anything.",
        ("list_dir",), ("list_dir",),
    ),
    BenchmarkTask(
        "FO-02", TaskType.FILE_OPS,
        "Create the directory C:\\benchmark\\reports and all required parents.",
        ("create_dir",), ("create_dir",),
    ),
    BenchmarkTask(
        "FO-03", TaskType.FILE_OPS,
        "Delete exactly the file C:\\benchmark\\obsolete.txt after the normal approval gate.",
        ("delete_file",), ("delete_file",),
    ),
)


def _schema_names(schemas: list[dict], arm: str) -> list[str]:
    if arm == "baseline":
        return [str(item.get("function", {}).get("name", "")) for item in schemas]
    return [str(item.get("function", {}).get("name", "")) for item in schemas]


def _parse_tool_calls(message: dict) -> list[dict]:
    parsed: list[dict] = []
    for item in message.get("tool_calls") or []:
        function = item.get("function") or {}
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        parsed.append({"name": str(function.get("name", "")), "arguments": arguments})
    return parsed


def score_selection(task: BenchmarkTask, arm: str, calls: list[dict], valid_names: set[str]) -> dict:
    expected = task.baseline_expected if arm == "baseline" else task.router_expected
    selected = calls[0]["name"] if calls else ""
    arguments = calls[0].get("arguments") if calls else {}
    correct = len(calls) == 1 and selected in expected
    request_target_ok = None
    if selected == "request_tool":
        request_target_ok = str((arguments or {}).get("name", "")) == task.request_target
        correct = correct and bool(request_target_ok)
    return {
        "selected_tool": selected,
        "selected_arguments": arguments,
        "tool_call_count": len(calls),
        "correct": bool(correct),
        "valid_tool": bool(selected and selected in valid_names),
        "request_target_ok": request_target_ok,
        "expected_tools": list(expected),
    }


def _post_ollama(model: str, messages: list[dict], schemas: list[dict], seed: int) -> tuple[dict, float]:
    payload = {
        "model": model,
        "messages": messages,
        "tools": schemas,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "seed": seed,
            "num_ctx": 32768,
            "num_predict": 256,
        },
    }
    started = time.perf_counter()
    response = requests.post(
        f"{OLLAMA_HOST.rstrip('/')}/api/chat",
        json=payload,
        timeout=600,
    )
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    return response.json(), elapsed


def summarize_rows(rows: list[dict]) -> dict:
    def arm_summary(arm: str) -> dict:
        selected = [row for row in rows if row["arm"] == arm]
        completed = [row for row in selected if not row.get("error")]
        prompt_tokens = [row["prompt_eval_count"] for row in completed]
        latencies = [row["elapsed_seconds"] for row in completed]
        by_category = {}
        for task_type in TaskType:
            category_rows = [row for row in completed if row["task_type"] == task_type.value]
            if category_rows:
                by_category[task_type.value] = {
                    "runs": len(category_rows),
                    "accuracy": sum(row["correct"] for row in category_rows) / len(category_rows),
                }
        return {
            "runs": len(selected),
            "completed": len(completed),
            "errors": len(selected) - len(completed),
            "accuracy": sum(row["correct"] for row in completed) / len(completed) if completed else 0.0,
            "invalid_tool_rate": sum(not row["valid_tool"] for row in completed) / len(completed) if completed else 0.0,
            "no_tool_rate": sum(row["tool_call_count"] == 0 for row in completed) / len(completed) if completed else 0.0,
            "multi_tool_rate": sum(row["tool_call_count"] != 1 for row in completed) / len(completed) if completed else 0.0,
            "avg_visible_tools": statistics.fmean(row["visible_tool_count"] for row in completed) if completed else 0.0,
            "avg_prompt_tokens": statistics.fmean(prompt_tokens) if prompt_tokens else 0.0,
            "median_prompt_tokens": statistics.median(prompt_tokens) if prompt_tokens else 0.0,
            "avg_latency_seconds": statistics.fmean(latencies) if latencies else 0.0,
            "median_latency_seconds": statistics.median(latencies) if latencies else 0.0,
            "by_category": by_category,
        }

    baseline = arm_summary("baseline")
    router = arm_summary("router")

    def reduction(new: float, old: float) -> float | None:
        return ((old - new) / old * 100.0) if old else None

    deltas = {
        "accuracy_percentage_points": (router["accuracy"] - baseline["accuracy"]) * 100.0,
        "prompt_token_reduction_percent": reduction(router["avg_prompt_tokens"], baseline["avg_prompt_tokens"]),
        "latency_reduction_percent": reduction(router["avg_latency_seconds"], baseline["avg_latency_seconds"]),
        "invalid_tool_percentage_points": (router["invalid_tool_rate"] - baseline["invalid_tool_rate"]) * 100.0,
    }
    recommended_pass = bool(
        router["accuracy"] >= baseline["accuracy"] - 0.05
        and (deltas["prompt_token_reduction_percent"] or 0.0) >= 20.0
        and router["invalid_tool_rate"] <= baseline["invalid_tool_rate"]
    )
    return {
        "baseline": baseline,
        "router": router,
        "deltas": deltas,
        "recommended_pilot_pass": recommended_pass,
        "note": "Pilot threshold only; use >=3 repeats before treating the result as stable.",
    }


def iter_runs(tasks: Iterable[BenchmarkTask], repeats: int) -> Iterable[tuple[int, BenchmarkTask, str]]:
    for repeat in range(repeats):
        for index, task in enumerate(tasks):
            arms = ("baseline", "router") if (index + repeat) % 2 == 0 else ("router", "baseline")
            for arm in arms:
                yield repeat + 1, task, arm


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemma4:12b")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--task", action="append", default=[], help="Run only a task ID; repeatable")
    parser.add_argument("--output-dir", default=str(PROJECT_DIR / "logs" / "benchmarks"))
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be >= 1")

    selected_tasks = [task for task in TASKS if not args.task or task.id in set(args.task)]
    if not selected_tasks:
        parser.error("No benchmark tasks matched --task")

    health = requests.get(f"{OLLAMA_HOST.rstrip('/')}/api/tags", timeout=5)
    health.raise_for_status()
    installed = {item.get("name") for item in health.json().get("models", [])}
    if args.model not in installed:
        raise RuntimeError(f"Ollama model is not installed: {args.model}")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    jsonl_path = output_dir / f"{stamp}-tool-router-ab.jsonl"
    summary_path = output_dir / f"{stamp}-tool-router-ab-summary.json"

    registry = build_default_registry()
    baseline_schemas = registry.ollama_schemas()
    registry_names = {tool.name for tool in registry.tools}
    rows: list[dict] = []
    total = len(selected_tasks) * args.repeats * 2

    print(f"AXIO tool-router A/B: model={args.model} tasks={len(selected_tasks)} repeats={args.repeats} calls={total}")
    print(f"Results: {jsonl_path}")
    for run_index, (repeat, task, arm) in enumerate(iter_runs(selected_tasks, args.repeats), 1):
        router = DynamicToolRouter(registry, task.prompt, budget=8, visibility="dynamic")
        if arm == "baseline":
            schemas = baseline_schemas
            predicted_type = router.task_type.value
        else:
            schemas = router.schemas("ollama")
            predicted_type = router.task_type.value
        visible_names = _schema_names(schemas, arm)
        valid_names = registry_names | ({"request_tool"} if arm == "router" else set())
        seed = 42000 + repeat
        print(
            f"[{run_index:02d}/{total}] {task.id} {arm:<8} tools={len(schemas):02d} "
            f"type={predicted_type}",
            flush=True,
        )
        base_row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "model": args.model,
            "repeat": repeat,
            "task_id": task.id,
            "task_type": task.task_type.value,
            "predicted_task_type": predicted_type,
            "classification_correct": predicted_type == task.task_type.value,
            "prompt": task.prompt,
            "arm": arm,
            "visible_tool_count": len(schemas),
            "visible_tools": visible_names,
            "seed": seed,
        }
        try:
            data, elapsed = _post_ollama(
                args.model,
                [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": task.prompt}],
                schemas,
                seed,
            )
            message = data.get("message") or {}
            calls = _parse_tool_calls(message)
            scored = score_selection(task, arm, calls, valid_names)
            row = {
                **base_row,
                **scored,
                "elapsed_seconds": round(elapsed, 4),
                "prompt_eval_count": int(data.get("prompt_eval_count", 0) or 0),
                "eval_count": int(data.get("eval_count", 0) or 0),
                "total_duration_ns": int(data.get("total_duration", 0) or 0),
                "response_content": str(message.get("content") or ""),
            }
            print(
                f"           selected={row['selected_tool'] or '[none]'} "
                f"correct={row['correct']} prompt_tokens={row['prompt_eval_count']} "
                f"elapsed={row['elapsed_seconds']}s",
                flush=True,
            )
        except Exception as exc:
            row = {**base_row, "error": f"{type(exc).__name__}: {exc}"}
            print(f"           ERROR {row['error']}", flush=True)
        rows.append(row)
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "task_count": len(selected_tasks),
        "repeats": args.repeats,
        "result_file": str(jsonl_path),
        **summarize_rows(rows),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Summary: {summary_path}")
    return 0 if not any(row.get("error") for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
