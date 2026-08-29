"""Unified AXIO Code mode for local Ollama and Claude backends."""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from core import claude_runtime, pricing
from core.code_tools import CODE_TOOL_REGISTRY, summarize_arguments
from core.code_tools.router import (
    DynamicToolRouter,
    LoopGuard,
    TrajectoryLogger,
    classify_complexity,
    process_history,
    step_budget,
    truncate_observation,
)
from core.coding_skills import (
    build_code_plan_prompt,
    build_coding_system_prompt,
    format_skill_catalog,
)
from core.console_input import capture_summary, is_multiline_command, read_multiline_input
from core.config import (
    INPUT_MAX_CHARS,
    CODE_PYTHON_TIMEOUT,
    CODE_TOOL_ROUTING_MODE,
    LOCAL_ONLY,
    MODELS,
    TEXT_EXTENSIONS,
)
from core.file_context import SESSION_CONTEXT
from core.logger import AuditLogger
from core.mode_memory import ModeMemorySession
from core.models import ClaudeClient, OllamaClient
from core.ui import BOLD, CYAN, RESET, YELLOW, Spinner, err, lo, mode_banner, ok, warn
from harness.planner import run_orchestrated


# One registry is the source of truth for both backends and every local-model alias.
CODE_TOOLS = CODE_TOOL_REGISTRY
# Full schemas remain the default runtime policy. The dynamic subset mode is
# retained behind AXIO_CODE_TOOL_ROUTING_MODE=dynamic for controlled experiments.
TOOLS = CODE_TOOLS.ollama_schemas()
TOOLS_CLAUDE = CODE_TOOLS.claude_schemas()
TOOL_MAP = CODE_TOOLS.handler_map
TOOL_VISIBILITY_BUDGET = 8


def _approve_tool(tool, args: dict) -> bool:
    print(f"\n  {YELLOW}[AGENT] Requests {tool.risk} tool: {tool.name}{RESET}")
    print(f"  {lo('  ' + summarize_arguments(args))}")
    if tool.risk == "destructive":
        return input("  Type DELETE to allow permanent deletion: ").strip() == "DELETE"
    if tool.risk == "external":
        return input("  Type ALLOW to authorize the external action: ").strip() == "ALLOW"
    return input("  Allow? (y/n): ").strip().lower() == "y"


def execute_tool(name: str, args: dict, audit=None) -> str:
    return CODE_TOOLS.execute(name, args, approve=_approve_tool, audit=audit)


# Compatibility for integrations/tests that imported the original helpers.
tool_read_file = TOOL_MAP["read_file"]
tool_write_file = TOOL_MAP["write_file"]
tool_edit_file = TOOL_MAP["edit_file"]
tool_list_dir = TOOL_MAP["list_dir"]
tool_create_dir = TOOL_MAP["create_dir"]
tool_search_files = TOOL_MAP["search_files"]
tool_grep_files = TOOL_MAP["grep_files"]
tool_inspect_python_environment = TOOL_MAP["inspect_python_environment"]


def tool_run_command(command: str, working_dir: str = None, timeout_seconds: int = 120) -> str:
    return execute_tool("run_command", {
        "command": command,
        "working_dir": working_dir,
        "timeout_seconds": timeout_seconds,
    })


def tool_run_python(
    script_path: str,
    args: list[str] | None = None,
    working_dir: str = None,
    timeout_seconds: int = CODE_PYTHON_TIMEOUT,
) -> str:
    return execute_tool("run_python", {
        "script_path": script_path,
        "args": args,
        "working_dir": working_dir,
        "timeout_seconds": timeout_seconds,
    })


def tool_delete_file(path: str) -> str:
    return execute_tool("delete_file", {"path": path})


SYSTEM_PROMPT = build_coding_system_prompt()
MAX_CONSEC_NUDGES = 2
_OUTPUT_LIMIT_REASONS = {"length", "max_tokens"}
_NUDGE = (
    "Continue working: call the tools needed to FINISH and VERIFY the task. "
    "Do not only narrate. If the task is complete and verification_gate has "
    "passed after any mutation, reply with TASK_COMPLETE and a short summary."
)
_CONTINUE_OUTPUT = (
    "Your previous response reached the output budget. Continue exactly where it "
    "stopped. Do not restart, summarize, or omit earlier content. End with "
    "TASK_COMPLETE only when the full response is finished."
)


@dataclass
class CodePlan:
    task: str = ""
    steps: list[str] = field(default_factory=list)
    approved: bool = False

    def clear(self) -> None:
        self.task = ""
        self.steps.clear()
        self.approved = False

    @property
    def ready(self) -> bool:
        return bool(self.task and self.steps and self.approved)


def build_code_task(task: str, file_context: str = "", memory_prefix: str = "") -> str:
    parts = [part.strip() for part in (memory_prefix, file_context) if part and part.strip()]
    parts.append(task)
    return "\n\n".join(parts)


def parse_plan_steps(raw: str, maximum: int = 15) -> list[str]:
    """Extract bounded numbered steps without trusting model formatting."""
    steps: list[str] = []
    for line in (raw or "").splitlines():
        match = re.match(r"^\s*(\d{1,2})[.)]\s+(.+?)\s*$", line)
        if match:
            steps.append(f"{len(steps) + 1}. {match.group(2)}")
        if len(steps) >= maximum:
            break
    return steps


def _generate_plan(
    task: str,
    *,
    model: str,
    ollama: OllamaClient,
    claude: ClaudeClient | None,
) -> list[str]:
    prompt = build_code_plan_prompt(tuple(tool.name for tool in CODE_TOOLS.tools))
    user_message = f"Task: {task}\n\nReturn the execution plan now."
    spinner = Spinner("Generating read-only plan").start()
    try:
        if claude is not None:
            raw = claude.chat([{"role": "user", "content": user_message}], system=prompt, print_output=False)
        else:
            raw = ollama.chat_stream(
                model,
                [{"role": "system", "content": prompt}, {"role": "user", "content": user_message}],
                print_output=False,
            )
    except Exception as exc:
        spinner.stop()
        print(f"  {err(f'Plan generation failed: {exc}')}\n")
        return []
    spinner.stop()
    return parse_plan_steps(raw)


def _present_plan(task: str, steps: list[str]) -> bool:
    print(f"\n  {BOLD}{CYAN}PLAN MODE — read only{RESET}")
    print(f"  {lo(task)}\n")
    for step in steps:
        print(f"  {step}")
    print(f"\n  {lo(f'{len(steps)} bounded step(s). Tool approvals still apply during execute.')}")
    try:
        answer = input("  Approve this plan for later execution? (y/n): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return False
    return answer == "y"


def _is_complete_signal(text: str) -> bool:
    upper = (text or "").upper()
    return "TASK_COMPLETE" in upper or "TAREA_COMPLETA" in upper


def _strip_complete_signal(text: str) -> str:
    return re.sub(r"(?i)\b(TASK_COMPLETE|TAREA_COMPLETA)\b[:\-\s]*", "", text or "").strip()


def _active_workspace_roots() -> list[Path]:
    roots = [Path.cwd().resolve()]
    roots.extend(path.resolve().parent for path in SESSION_CONTEXT.files)
    return list(dict.fromkeys(roots))


def _completion_gate() -> tuple[bool, str]:
    """Combine the verification gate and the web-evidence gate into one verdict.

    Either unmet gate blocks TASK_COMPLETE; the verification reason takes
    precedence when both are unmet so the user first sees the code-safety issue.
    """
    allowed, v_reason = CODE_TOOLS.completion_status()
    if not allowed:
        return False, v_reason
    web_ok, w_reason = CODE_TOOLS.web_completion_status()
    if not web_ok:
        return False, w_reason
    return True, v_reason


def _completion_or_nudge(content: str, nudges: int) -> tuple[str, int]:
    complete = _is_complete_signal(content)
    allowed, reason = _completion_gate()
    if complete and not allowed:
        if nudges >= MAX_CONSEC_NUDGES:
            return f"Agent stopped without verification: {reason}", nudges
        return "", nudges + 1
    if complete or nudges >= MAX_CONSEC_NUDGES:
        if not allowed:
            return f"Agent stopped without verification: {reason}", nudges
        return _strip_complete_signal(content), nudges
    return "", nudges + 1


def read_multiline_task(input_fn=None, max_chars: int = INPUT_MAX_CHARS) -> str:
    """Backward-compatible Code wrapper around the shared console reader."""
    return read_multiline_input(input_fn=input_fn, max_chars=max_chars)


def handle_context_command(command: str, original_task: str) -> tuple[bool, str]:
    """Dispatch Code's native/manual file-context commands."""
    if command in {"loaded", "context"}:
        return True, SESSION_CONTEXT.list_str()
    if command == "browse":
        return True, SESSION_CONTEXT.load_browse_folder()
    if command in {"browse file", "browse files"}:
        return True, SESSION_CONTEXT.load_browse_files()
    if command.startswith("load "):
        marker = original_task.lower().find("load ")
        return True, SESSION_CONTEXT.load_path(original_task[marker + 5:].strip())
    if command in {"unload", "clear files"}:
        return True, SESSION_CONTEXT.clear()
    return False, ""


def _run_ollama_agent(
    task: str,
    model: str,
    ollama: OllamaClient,
    logger: AuditLogger,
    image_messages: list[dict] | None = None,
    task_scope: str | None = None,
) -> str:
    scoped_task = task_scope or task
    CODE_TOOLS.start_task(scoped_task, _active_workspace_roots())
    router = DynamicToolRouter(
        CODE_TOOLS,
        scoped_task,
        budget=TOOL_VISIBILITY_BUDGET,
        visibility=CODE_TOOL_ROUTING_MODE,
    )
    guard = LoopGuard()
    trajectory = TrajectoryLogger("code-ollama")
    max_steps = step_budget(scoped_task)
    messages = [{"role": "system", "content": build_coding_system_prompt(task)}]
    messages.extend(image_messages or [])
    messages.append({"role": "user", "content": task})
    print(
        f"\n  {lo(f'model: {model} | tools: {len(CODE_TOOLS.tools)}/{len(CODE_TOOLS.tools)} '
        f'| routing: {CODE_TOOL_ROUTING_MODE} | complexity: {classify_complexity(scoped_task)} '
        f'| max steps: {max_steps}')}\n"
    )
    started = time.time()
    nudges = 0
    pending_answer_parts: list[str] = []

    for iteration in range(max_steps):
        messages = process_history(messages, "ollama")
        active_schemas = router.schemas("ollama")
        spinner = Spinner(f"[{model}] step {iteration + 1}").start()
        try:
            data = ollama.tool_call(model, messages, active_schemas)
        except Exception as exc:
            spinner.stop()
            failure = f"Ollama error: {exc}"
            trajectory.log_step(
                step=iteration + 1,
                task_type=router.task_type,
                active_tools=router.exposed_names,
                tool_call=None,
                observation_raw=failure,
                observation_truncated=truncate_observation(failure),
                event="error",
            )
            return failure
        spinner.stop()
        message = data.get("message", {})
        calls = message.get("tool_calls", [])
        content = (message.get("content") or "").strip()
        done_reason = str(data.get("done_reason") or "").lower()

        if not calls:
            trajectory.log_step(
                step=iteration + 1,
                task_type=router.task_type,
                active_tools=router.exposed_names,
                tool_call=None,
                observation_raw=content,
                observation_truncated=truncate_observation(content),
                event="assistant",
            )
            if content and done_reason in _OUTPUT_LIMIT_REASONS:
                pending_answer_parts.append(content)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": _CONTINUE_OUTPUT})
                print(f"  {lo('(output limit reached; continuing without dropping content...)')}")
                continue

            complete_content = "\n".join(
                [*pending_answer_parts, content] if content else pending_answer_parts
            ).strip()
            final, next_nudges = _completion_or_nudge(complete_content, nudges)
            if final:
                elapsed = round(time.time() - started, 1)
                print(f"\n  {CYAN}[{model}]{RESET} {final}")
                print(f"\n  {lo(f'Done in {iteration + 1} step(s), {elapsed}s')}\n")
                return final
            nudges = next_nudges
            if content:
                pending_answer_parts.append(content)
            allowed, reason = _completion_gate()
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": _NUDGE + (" " + reason if not allowed else "")})
            print(f"  {lo('(continue) requesting tool execution or verified completion...')}")
            continue

        nudges = 0
        pending_answer_parts.clear()
        messages.append({"role": "assistant", "content": content, "tool_calls": calls})
        interventions: list[str] = []
        for call in calls:
            function = call.get("function", {})
            name = function.get("name", "")
            args = function.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            print(f"  {YELLOW}{name}{RESET}({summarize_arguments(args, limit=50)})")
            routed = router.handle_unavailable_call(name, args)
            if routed is None:
                result = execute_tool(
                    name,
                    args,
                    audit=lambda tool, tool_args, output: logger.log_tool(
                        task, tool.name, tool_args, output, model
                    ),
                )
                record = CODE_TOOLS.records[-1] if CODE_TOOLS.records else None
                mutation_success = bool(
                    record and record.ok and record.risk in {"write", "destructive"}
                )
            else:
                result = routed
                mutation_success = False
            truncated = truncate_observation(result)
            router.observe(truncated)
            intervention = guard.record(name, args, truncated, mutation_success)
            if intervention:
                interventions.append(intervention)
            trajectory.log_step(
                step=iteration + 1,
                task_type=router.task_type,
                active_tools=router.exposed_names,
                tool_call={"name": name, "arguments": args},
                observation_raw=result,
                observation_truncated=truncated,
            )
            preview = result[:100].replace("\n", " ")
            print(f"  {lo('  ' + preview + ('...' if len(result) > 100 else ''))}")
            messages.append({"role": "tool", "content": truncated})
        if interventions:
            messages.append({"role": "user", "content": "\n".join(interventions)})
        if guard.should_stop:
            result = "Agent stopped: repeated no-progress interventions exhausted the harness guard."
            print(f"  {warn(result)}")
            return result

    result = f"Agent stopped: reached adaptive max {max_steps} steps"
    print(f"  {warn(result)}")
    return result


def _run_claude_agent(
    task: str,
    claude: ClaudeClient,
    logger: AuditLogger,
    task_scope: str | None = None,
) -> str:
    scoped_task = task_scope or task
    CODE_TOOLS.start_task(scoped_task, _active_workspace_roots())
    router = DynamicToolRouter(
        CODE_TOOLS,
        scoped_task,
        budget=TOOL_VISIBILITY_BUDGET,
        visibility=CODE_TOOL_ROUTING_MODE,
    )
    guard = LoopGuard()
    trajectory = TrajectoryLogger("code-claude")
    max_steps = step_budget(scoped_task)
    system_prompt = build_coding_system_prompt(task)
    messages = [{"role": "user", "content": task}]
    usage = {}
    nudges = 0
    pending_answer_parts: list[str] = []
    started = time.time()
    model = claude_runtime.get_model()
    print(
        f"\n  {lo(f'model: {claude_runtime.describe()} (Claude API) | '
        f'tools: {len(CODE_TOOLS.tools)}/{len(CODE_TOOLS.tools)} | routing: {CODE_TOOL_ROUTING_MODE} | '
        f'complexity: {classify_complexity(scoped_task)} | max steps: {max_steps}')}\n"
    )

    def report_cost() -> None:
        print(f"  {lo(pricing.summarize(model, usage))}")
        log_usage = getattr(logger, "log_usage", None)
        if log_usage:
            log_usage(model, pricing.tokens(usage), pricing.cost_usd(model, usage), route="code", elapsed=round(time.time() - started, 1))

    for iteration in range(max_steps):
        messages = process_history(messages, "claude")
        active_schemas = router.schemas("claude")
        spinner = Spinner(f"[Claude] step {iteration + 1}").start()
        try:
            response = claude.tool_call(messages, active_schemas, system=system_prompt)
        except Exception as exc:
            spinner.stop()
            failure = f"Claude error: {exc}"
            trajectory.log_step(
                step=iteration + 1,
                task_type=router.task_type,
                active_tools=router.exposed_names,
                tool_call=None,
                observation_raw=failure,
                observation_truncated=truncate_observation(failure),
                event="error",
            )
            return failure
        spinner.stop()
        if response is None:
            return "Claude returned no response"
        pricing.add(usage, getattr(response, "usage", None))
        text_parts = [block.text for block in response.content if block.type == "text"]
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use" or not tool_uses:
            content = "\n".join(text_parts).strip()
            trajectory.log_step(
                step=iteration + 1,
                task_type=router.task_type,
                active_tools=router.exposed_names,
                tool_call=None,
                observation_raw=content,
                observation_truncated=truncate_observation(content),
                event="assistant",
            )
            if content and str(response.stop_reason).lower() in _OUTPUT_LIMIT_REASONS:
                pending_answer_parts.append(content)
                messages.append({"role": "user", "content": _CONTINUE_OUTPUT})
                print(f"  {lo('(output limit reached; continuing without dropping content...)')}")
                continue

            complete_content = "\n".join(
                [*pending_answer_parts, content] if content else pending_answer_parts
            ).strip()
            final, next_nudges = _completion_or_nudge(complete_content, nudges)
            if final:
                print(f"\n  {CYAN}[Claude]{RESET} {final}")
                print(f"\n  {lo(f'Done in {iteration + 1} step(s), {round(time.time() - started, 1)}s')}")
                report_cost()
                print()
                return final
            nudges = next_nudges
            if content:
                pending_answer_parts.append(content)
            allowed, reason = _completion_gate()
            messages.append({"role": "user", "content": _NUDGE + (" " + reason if not allowed else "")})
            print(f"  {lo('(continue) requesting tool execution or verified completion...')}")
            continue

        nudges = 0
        pending_answer_parts.clear()
        results = []
        interventions: list[str] = []
        for tool_use in tool_uses:
            args = tool_use.input if isinstance(tool_use.input, dict) else {}
            print(f"  {YELLOW}{tool_use.name}{RESET}({summarize_arguments(args, limit=50)})")
            routed = router.handle_unavailable_call(tool_use.name, args)
            if routed is None:
                output = execute_tool(
                    tool_use.name,
                    args,
                    audit=lambda tool, tool_args, result: logger.log_tool(
                        task, tool.name, tool_args, result, claude_runtime.get_model()
                    ),
                )
                record = CODE_TOOLS.records[-1] if CODE_TOOLS.records else None
                mutation_success = bool(
                    record and record.ok and record.risk in {"write", "destructive"}
                )
            else:
                output = routed
                mutation_success = False
            truncated = truncate_observation(output)
            router.observe(truncated)
            intervention = guard.record(tool_use.name, args, truncated, mutation_success)
            if intervention:
                interventions.append(intervention)
            trajectory.log_step(
                step=iteration + 1,
                task_type=router.task_type,
                active_tools=router.exposed_names,
                tool_call={"name": tool_use.name, "arguments": args},
                observation_raw=output,
                observation_truncated=truncated,
            )
            preview = output[:100].replace("\n", " ")
            print(f"  {lo('  ' + preview + ('...' if len(output) > 100 else ''))}")
            results.append({"type": "tool_result", "tool_use_id": tool_use.id, "content": truncated})
        if interventions:
            results.append({"type": "text", "text": "\n".join(interventions)})
        messages.append({"role": "user", "content": results})
        if guard.should_stop:
            result = "Agent stopped: repeated no-progress interventions exhausted the harness guard."
            print(f"  {warn(result)}")
            report_cost()
            return result

    result = f"Agent stopped: reached adaptive max {max_steps} steps"
    print(f"  {warn(result)}")
    report_cost()
    return result


def _load_local_image(path_text: str) -> tuple[str, dict | None]:
    path = Path(path_text.strip().strip('"').strip("'")).expanduser()
    if not path.is_absolute() or not path.is_file():
        return f"Image not found at an absolute file path: {path}", None
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return f"Unsupported image format: {path.suffix}", None
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        return f"Could not read image: {exc}", None
    message = {"role": "user", "content": f"Local image: {path.name}", "images": [encoded]}
    return f"Loaded local image: {path}", message


HELP = f"""
{BOLD}Coding:{RESET}
  Type a task for direct execution.
  {YELLOW}paste{RESET}              Capture a large multiline task; finish with ::end
  {YELLOW}plan <task>{RESET}        Generate a read-only plan and approve it
  {YELLOW}execute{RESET}            Execute the last approved plan
  {YELLOW}agents <task>{RESET}      Multi-agent orchestrator: plan → specialist agents → synthesis
  {YELLOW}vision <path>{RESET}      Attach a local image to Ollama context

{BOLD}Inspection:{RESET}
  {YELLOW}tools{RESET}              List the canonical {len(TOOLS)} tools and risk levels
  {YELLOW}skills{RESET}             List the single curated Code skill set
  {YELLOW}loaded{RESET}             Show shared file context
  {YELLOW}browse{RESET}             Open the native folder selector
  {YELLOW}browse files{RESET}       Open the native multi-file selector
  {YELLOW}load <path>{RESET}        Load a file or folder as workspace context
  {YELLOW}unload{RESET}             Clear loaded files and folders

{BOLD}Runtime:{RESET}
  {YELLOW}model{RESET}              Show active model
  {YELLOW}model <name>{RESET}       Local: select Ollama model; cloud: select Claude alias/id
  {YELLOW}effort <level>{RESET}     Claude effort: low, medium, high, xhigh, max
  {YELLOW}memory status{RESET}      Show Code memory backend status
  {YELLOW}clear{RESET}              Clear approved plan and attached images
  {YELLOW}help{RESET} / {YELLOW}exit{RESET}
"""


def run(force_claude_session: bool = False) -> None:
    mode_banner("code", f"Unified coding agent  |  {len(TOOLS)} tools  |  Plan Mode  |  agents  |  verification gate")
    ollama = OllamaClient()
    logger = AuditLogger("code")
    memory = ModeMemorySession("code")
    model = MODELS["coding"]
    plan = CodePlan()
    images: list[dict] = []
    # Code accepts the complete maintained text/code extension set in addition
    # to the shared context defaults used by the other modes.
    SESSION_CONTEXT.extensions.update(TEXT_EXTENSIONS)

    if LOCAL_ONLY:
        claude = None
        if not ollama.is_running():
            print(f"  {err('Ollama offline. Run: ollama serve')}\n")
            return
        print(f"  Local agent: {ok('READY')} ({model})    Claude API: {lo('OFF (local-only)')}\n")
    else:
        try:
            claude = ClaudeClient()
        except Exception:
            print(f"  {err('Code mode requires ANTHROPIC_API_KEY when LOCAL_ONLY=0.')}\n")
            return
        print(f"  Local agent: {ok('READY')} ({model})    Claude API: {ok('READY')}\n")
        print(f"  {ok('Claude API mode')}  {lo('— use LOCAL_ONLY=1 for on-device execution')}\n")

    if force_claude_session and LOCAL_ONLY:
        print(f"  {warn('--claude ignored because LOCAL_ONLY=1')}\n")
    print(f"  {lo('Type')} {YELLOW}help{RESET} {lo('for commands. Type')} {YELLOW}exit{RESET} {lo('to quit.')}\n")

    while True:
        labels = ["Local" if LOCAL_ONLY else "Claude"]
        if plan.ready:
            labels.append("Plan approved")
        if SESSION_CONTEXT.count:
            labels.append(f"{SESSION_CONTEXT.count} files")
        try:
            task = input(f"  {YELLOW}CODE›{RESET} {lo('[' + ' | '.join(labels) + ']')} ").strip()
        except (KeyboardInterrupt, EOFError):
            memory.store(ollama_client=ollama)
            print(f"\n  {ok('Goodbye.')}\n")
            break
        if not task:
            continue
        lower = task.lower()
        command = lower[1:] if lower.startswith("/") else lower
        multiline = False

        if is_multiline_command(task):
            try:
                task = read_multiline_task()
            except ValueError as exc:
                print(f"  {warn(str(exc))}\n")
                continue
            if not task.strip():
                print(f"  {lo('Multiline input cancelled or empty.')}\n")
                continue
            multiline = True
            command = ""
            print(f"  {ok(capture_summary(task))}\n")

        if command in {"exit", "quit"}:
            memory.store(ollama_client=ollama)
            print(f"  {ok('Goodbye.')}\n")
            break
        if command == "help":
            print(HELP)
            continue
        if command == "tools":
            print(f"\n  {BOLD}Available tools ({len(TOOLS)}):{RESET}")
            print(CODE_TOOLS.format_catalog())
            print()
            continue
        if command == "skills":
            print(f"\n{format_skill_catalog()}\n")
            continue
        if command == "agents" or command.startswith("agents "):
            agent_task = task.split(maxsplit=1)[1].strip() if " " in task else ""
            if not agent_task:
                print(f"  {warn('Usage: agents <task>  — plan the task and run the specialist agent fleet')}\n")
                continue
            provider = "ollama" if LOCAL_ONLY else "claude"
            active_model = model if LOCAL_ONLY else claude_runtime.get_model()
            file_context = SESSION_CONTEXT.inject("", mode="list").strip() if SESSION_CONTEXT.count else ""
            scoped = build_code_task(agent_task, file_context, "")
            CODE_TOOLS.start_task(agent_task, _active_workspace_roots())
            audit = lambda tool, targs, out: logger.log_tool(agent_task, tool.name, targs, out, active_model)
            memory.record_user(agent_task, metadata={"mode": "agents", "backend": provider})
            print(f"  {lo('Multi-agent orchestrator — plan, dispatch, peer-delegate, synthesize.')}")
            try:
                summary = run_orchestrated(
                    scoped, provider=provider,
                    model=(model if LOCAL_ONLY else None),
                    ollama=ollama, claude=claude,
                    approve=_approve_tool, audit=audit,
                    memory_prefix=memory.prefix(agent_task),
                )
            except Exception as exc:
                print(f"  {err(f'Orchestrator error: {exc}')}\n")
                continue
            print(f"\n{summary}\n")
            memory.record_assistant(summary, model=active_model, metadata={"mode": "agents"})
            continue
        context_handled, context_result = handle_context_command(command, task)
        if context_handled:
            print(f"{context_result}\n")
            continue
        if command == "clear":
            plan.clear()
            images.clear()
            print(f"  {ok('Plan and image context cleared.')}\n")
            continue
        if command == "model":
            active = model if LOCAL_ONLY else claude_runtime.describe()
            print(f"  Active model: {active}\n")
            continue
        if command.startswith("model "):
            requested = task.split(maxsplit=1)[1].strip()
            if LOCAL_ONLY:
                model = MODELS["coding"] if requested.lower() in {"gemma", "local"} else requested
                print(f"  Local model set to: {CYAN}{model}{RESET}\n")
            else:
                parts = requested.split()
                selected, effort, valid = claude_runtime.apply(parts[0], parts[1] if len(parts) > 1 else None)
                print(f"  {ok(f'Claude model: {selected} | effort={effort}')}\n" if valid else f"  {warn(claude_runtime.options())}\n")
            continue
        if command.startswith("effort "):
            if LOCAL_ONLY:
                print(f"  {warn('Claude effort is inactive while LOCAL_ONLY=1.')}\n")
                continue
            selected = claude_runtime.set_effort(command.split(maxsplit=1)[1])
            print(f"  {ok(f'Effort: {selected}')}\n" if selected else f"  {warn(claude_runtime.options())}\n")
            continue
        if command.startswith("vision "):
            if not LOCAL_ONLY:
                print(f"  {warn('vision is local-only in this Code adapter; no image was sent to cloud.')}\n")
                continue
            status, message = _load_local_image(task[task.lower().find("vision ") + 7:])
            if message:
                images.append(message)
                print(f"  {ok(status)}\n")
            else:
                print(f"  {err(status)}\n")
            continue
        if command.startswith("plan "):
            description = task[task.lower().find("plan ") + 5:].strip()
            plan.clear()
            steps = _generate_plan(description, model=model, ollama=ollama, claude=claude)
            if not steps:
                print(f"  {warn('No valid numbered plan was returned.')}\n")
                continue
            if _present_plan(description, steps):
                plan.task, plan.steps, plan.approved = description, steps, True
                print(f"  {ok('Plan approved. Type execute to run it through the normal tool gates.')}\n")
            else:
                print(f"  {warn('Plan cancelled.')}\n")
            continue
        if command == "plan":
            if not plan.steps:
                print(f"  {lo('No plan in this session.')}\n")
            else:
                print("\n".join(plan.steps) + "\n")
            continue
        if command == "execute":
            if not plan.ready:
                print(f"  {warn('No approved plan. Use plan <task> first.')}\n")
                continue
            user_task = f"Execute the approved plan for this task: {plan.task}\n\n" + "\n".join(plan.steps)
        else:
            if not multiline and memory.handle_command(command):
                continue
            user_task = task

        file_context = SESSION_CONTEXT.inject("", mode="list").strip() if SESSION_CONTEXT.count else ""
        final_task = build_code_task(user_task, file_context, memory.prefix(user_task))
        active_model = model if LOCAL_ONLY else claude_runtime.get_model()
        metadata = {"backend": "ollama" if LOCAL_ONLY else "claude", "workspace_files": SESSION_CONTEXT.count}
        memory.record_user(user_task, metadata=metadata)
        if LOCAL_ONLY:
            result = _run_ollama_agent(
                final_task,
                model,
                ollama,
                logger,
                image_messages=images,
                task_scope=user_task,
            )
        else:
            result = _run_claude_agent(final_task, claude, logger, task_scope=user_task)
        if result.startswith(("Ollama error:", "Claude error:")):
            print(f"  {err(result)}\n")
        memory.record_assistant(result, model=active_model, metadata=metadata)
