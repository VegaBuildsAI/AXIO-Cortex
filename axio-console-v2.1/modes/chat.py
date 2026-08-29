"""
AXIO Chat Mode
General-purpose conversational AI with persistent sessions.
Equivalent to Claude Chat — back-and-forth conversation with memory,
switchable between local Ollama models and the Claude API backend.

Commands:
  /help              Show commands
  /paste             Capture a large multiline message
  /models            List available Ollama models
  /switch <model>    Switch active model
  /backend           Toggle between Ollama ↔ Claude
  /new [name]        Start a new session
  /sessions          List all saved sessions
  /load <name>       Load a saved session
  /save              Save current session
  /clear             Clear message history
  /delete <name>     Delete a saved session
  /info              Show current session info
  /exit              Save and quit
"""

from core.models       import OllamaClient, ClaudeClient
from core.session      import SessionManager
from core.logger       import AuditLogger
from core.file_context import SESSION_CONTEXT
from core.web_intent   import augment_with_web
from core.console_input import capture_summary, is_multiline_command, read_multiline_input
from core.config       import MODELS, LOCAL_ONLY
from core.mode_memory  import ModeMemorySession
from core.code_tools   import CODE_TOOL_REGISTRY
from core.code_tools.tool_loop import run_tool_loop
from core.code_tools.profiles  import CHAT_TOOLS
from pathlib import Path

# Chat is a conversation first: keep the tool budget small so a plain reply
# still returns in a single round when no tool is needed.
CHAT_TOOL_STEPS = 4
CHAT_SYSTEM = (
    "You are AXIO Chat, a helpful assistant. You can read and write files, "
    "create Word/Excel/PowerPoint/PDF documents, and search, fetch, and browse "
    "the web. Use a tool only when it genuinely helps; otherwise just answer."
)
from core.ui           import (
    mode_banner, status_line, divider,
    CYAN, YELLOW, GREEN, RED, PURPLE, DIM, BOLD, RESET, ok, warn, err, hi, lo
)


HELP = f"""
{BOLD}Commands:{RESET}
  {YELLOW}/help{RESET}              Show this message
  {YELLOW}/paste{RESET}             Capture multiline text; finish with ::end
  {YELLOW}/models{RESET}            List available Ollama models
  {YELLOW}/switch <model>{RESET}    Switch active local model
  {YELLOW}/backend{RESET}           Toggle Ollama ↔ Claude API
  {YELLOW}/new [name]{RESET}        Start a new session
  {YELLOW}/sessions{RESET}          List saved sessions
  {YELLOW}/load <name>{RESET}       Load a saved session
  {YELLOW}/save{RESET}              Save current session
  {YELLOW}/clear{RESET}             Clear message history
  {YELLOW}/delete <name>{RESET}     Delete a saved session
  {YELLOW}/info{RESET}              Session info
  {YELLOW}/exit{RESET}              Save and quit
"""


def _select_default_chat_model(models: list[dict], configured_model: str) -> str:
    """Keep the configured generation model; never select an embedder by list order."""
    del models
    return configured_model


def _store_chat_memory(sm, memory: ModeMemorySession, session: dict, ollama) -> None:
    """Persist SessionManager state and the durable ModeMemorySession on exit."""
    sm.save(session)
    if memory.session.get("messages"):
        memory.store(ollama_client=ollama)


def run(initial_model: str = "", initial_session: str = None):
    """Entry point called by axio.py."""
    mode_banner("chat", "General-purpose conversational AI  |  Ollama + Claude")

    ollama = OllamaClient()
    sm     = SessionManager()
    logger = AuditLogger("chat")
    memory = ModeMemorySession("chat")

    # Try to init Claude (optional)
    try:
        if LOCAL_ONLY:
            raise RuntimeError("local-only")
        claude = ClaudeClient()
        claude_ok = True
        print(f"  Ollama: {ok('ONLINE ✓')}    Claude API: {ok('READY ✓')}\n")
    except Exception:
        claude    = None
        claude_ok = False
        cloud_label = "OFF (local-only)" if LOCAL_ONLY else "OFFLINE"
        print(f"  Ollama: {ok('ONLINE ✓')}    Claude API: {warn(cloud_label)}\n")

    # Resolve active model
    models = ollama.list_models()
    model = initial_model or _select_default_chat_model(models, MODELS["chat"])

    # Init or resume session
    if initial_session:
        session = sm.load(initial_session) or sm.new(initial_session, model, "chat")
    else:
        session = sm.new(model=model, mode="chat")

    print(f"  {lo('Type')} {YELLOW}/help{RESET} {lo('for commands.  Ctrl+C or')} {YELLOW}/exit{RESET} {lo('to quit.')}\n")
    logger.log_event("session_start", session["name"])

    while True:
        try:
            backend = session.get("backend", "ollama")
            status_line("chat", session["name"], session.get("model", model),
                        sm.message_count(session), backend)

            prompt = input(f"  {CYAN}CHAT›{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            _store_chat_memory(sm, memory, session, ollama)
            print(f"\n  {ok('Session saved.')} Goodbye.\n")
            break

        if not prompt:
            continue

        multiline = False
        if is_multiline_command(prompt):
            try:
                prompt = read_multiline_input()
            except ValueError as exc:
                print(f"  {warn(str(exc))}\n")
                continue
            if not prompt.strip():
                print(f"  {lo('Multiline input cancelled or empty.')}\n")
                continue
            multiline = True
            print(f"  {ok(capture_summary(prompt))}\n")

        # ── slash commands ────────────────────────────────────────
        if prompt.startswith("/") and not multiline:
            parts = prompt.split(maxsplit=1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts) > 1 else ""

            if cmd in ("/exit", "/quit"):
                _store_chat_memory(sm, memory, session, ollama)
                print(f"  {ok('Session saved.')} Goodbye.\n")
                break

            elif cmd.startswith("/memory") and memory.handle_command(prompt[1:]):
                continue

            elif cmd == "/help":
                print(HELP)

            elif cmd == "/models":
                mdls = ollama.list_models()
                if mdls:
                    print(f"\n  {BOLD}Available models:{RESET}")
                    for m in mdls:
                        marker = ok(" ◀ active") if m["name"] == session.get("model", model) else ""
                        print(f"    {CYAN}{m['name']}{RESET}{marker}")
                    print()
                else:
                    print(f"  {warn('No models found — is Ollama running?')}\n")

            elif cmd == "/switch":
                if arg:
                    session["model"] = arg
                    print(f"  {ok(f'Switched to: {arg}')}\n")
                else:
                    print(f"  {warn('Usage: /switch <model_name>')}\n")

            elif cmd == "/backend":
                if backend == "ollama":
                    if claude_ok:
                        session["backend"] = "claude"
                        print(f"  Backend → {hi('Claude API')}\n")
                    else:
                        print(f"  {err('Claude API not available. Add ANTHROPIC_API_KEY to .env')}\n")
                else:
                    session["backend"] = "ollama"
                    print(f"  Backend → {ok('Ollama')}\n")

            elif cmd == "/new":
                sm.save(session)
                session = sm.new(arg or None, session.get("model", model), "chat")
                sname = session["name"]
                print(f"  {ok(f'New session: {sname}')}\n")

            elif cmd == "/sessions":
                all_sessions = sm.list_sessions()
                if all_sessions:
                    print(f"\n  {BOLD}Saved sessions:{RESET}")
                    for s in all_sessions:
                        active   = ok(" ◀ current") if s["name"] == session["name"] else ""
                        n_msgs   = len(s.get("messages", []))
                        backend  = s.get("backend", "ollama")
                        print(f"    {GREEN}{s['name']}{RESET}  {lo(backend)}  {lo(f'{n_msgs} msgs')}{active}")
                    print()
                else:
                    print(f"  {lo('No saved sessions yet.')}\n")

            elif cmd == "/load":
                if arg:
                    loaded = sm.load(arg)
                    if loaded:
                        sm.save(session)
                        session = loaded
                        sname   = session["name"]
                        print(f"  {ok(f'Loaded: {sname}')}\n")
                    else:
                        print(f"  {err(f'Session not found: {arg}')}\n")
                else:
                    print(f"  {warn('Usage: /load <name>')}\n")

            elif cmd == "/save":
                sm.save(session)
                sname = session["name"]
                print(f"  {ok(f'Saved: {sname}')}\n")

            elif cmd == "/clear":
                count = sm.clear(session)
                print(f"  {ok(f'Cleared {count} messages.')}\n")

            elif cmd == "/delete":
                if arg:
                    if sm.delete(arg):
                        print(f"  {ok(f'Deleted: {arg}')}\n")
                    else:
                        print(f"  {err(f'Not found: {arg}')}\n")
                else:
                    print(f"  {warn('Usage: /delete <name>')}\n")

            elif cmd == "/info":
                cur_model = session.get("model", model)
                print(f"""
  {BOLD}Session Info{RESET}
  {"─"*30}
  Name     : {GREEN}{session['name']}{RESET}
  Mode     : chat
  Backend  : {GREEN if backend == 'ollama' else CYAN}{backend}{RESET}
  Model    : {YELLOW}{cur_model}{RESET}
  Messages : {sm.message_count(session)}
  Created  : {lo(session.get('created','—'))}
  Updated  : {lo(session.get('updated','—'))}
""")

            # ── shared file context ───────────────────────────────
            elif cmd == "/browse":
                print(SESSION_CONTEXT.load_browse_folder())

            elif cmd in ("/browse files", "/browsefiles"):
                print(SESSION_CONTEXT.load_browse_files())

            elif cmd == "/load":
                if arg:
                    print(SESSION_CONTEXT.load_path(arg))
                else:
                    print(f"  {warn('Usage: /load <file or folder path>')}\n")

            elif cmd in ("/loaded", "/context", "/files"):
                print(SESSION_CONTEXT.list_str())

            elif cmd in ("/unload", "/clearfiles"):
                print(SESSION_CONTEXT.clear())

            else:
                print(f"  {err(f'Unknown command: {cmd}')}  Type /help for commands.\n")

        # ── chat turn ─────────────────────────────────────────────
        else:
            cur_backend = session.get("backend", "ollama")
            cur_model   = session.get("model", model)
            # inject shared file context if files are loaded
            memory_prefix = memory.prefix(prompt)
            chat_prompt = SESSION_CONTEXT.inject(prompt, mode="block") if SESSION_CONTEXT.count else prompt
            if memory_prefix:
                chat_prompt = memory_prefix.strip() + "\n\n" + chat_prompt
            # Web-augmentation: for current-information questions, retrieve and
            # cite live evidence instead of answering from memory (Ollama and
            # Claude alike; empty for non-web questions).
            web_evidence = augment_with_web(prompt)
            if web_evidence:
                chat_prompt = (
                    "Answer using the web evidence below and cite the source URLs. "
                    "Do not answer from memory when evidence is present.\n\n"
                    + web_evidence.strip() + "\n\n" + chat_prompt
                )
            messages    = session["messages"] + [{"role": "user", "content": chat_prompt}]

            divider()
            response = ""
            # Tools draw from the chat profile of the 42-tool registry; the
            # registry's own risk/approval gate still guards every call. Scope
            # the workspace to cwd so in-directory writes don't prompt.
            CODE_TOOL_REGISTRY.start_task(prompt, [Path.cwd()])
            audit = lambda tool, targs, out: logger.log_tool(prompt, tool.name, targs, out, cur_model)

            if cur_backend == "claude":
                if not claude_ok:
                    print(f"  {err('Claude not available.')}\n")
                    continue
                print(f"\n  {PURPLE}[Claude]{RESET}")
                try:
                    response = run_tool_loop(
                        tool_names=CHAT_TOOLS, provider="claude",
                        messages=list(messages), claude=claude,
                        system=CHAT_SYSTEM, audit=audit, max_steps=CHAT_TOOL_STEPS,
                    )
                    print(f"  {response}")
                except Exception as e:
                    print(f"\n  {err(f'Error: {e}')}\n")
                    continue
            else:
                if not ollama.is_running():
                    print(f"  {err('Ollama is offline. Run: ollama serve')}\n")
                    continue
                print(f"\n  {CYAN}[{cur_model}]{RESET}")
                try:
                    response = run_tool_loop(
                        tool_names=CHAT_TOOLS, provider="ollama",
                        messages=list(messages), ollama=ollama, model=cur_model,
                        audit=audit, max_steps=CHAT_TOOL_STEPS,
                    )
                    print(f"  {response}")
                except Exception:
                    # Model may not support tool-calling — fall back to plain streaming chat.
                    print(f"  {lo('(tools unavailable for this model — plain chat)')}")
                    try:
                        response = ollama.chat_stream(cur_model, messages)
                    except Exception as e:
                        print(f"\n  {err(f'Error: {e}')}\n")
                        continue

            divider()
            print()

            sm.add_turn(session, prompt, response)
            sm.save(session)
            memory.record_turn(prompt, response, model=cur_model, metadata={"backend": cur_backend})
            logger.log_turn(prompt, response, cur_model, route=cur_backend)
