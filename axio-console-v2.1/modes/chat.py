"""
AXIO Chat Mode
General-purpose conversational AI with persistent sessions.
Equivalent to Claude Chat — back-and-forth conversation with memory,
switchable between local Ollama models and the Claude API backend.

Commands:
  /help              Show commands
  /models            List available Ollama models
  /switch <model>    Switch active model
  /backend           Toggle between Ollama ↔ Claude
  /new [name]        Start a new session
  /sessions          List all saved sessions
  /load <name>       Load a saved session
  /loadfile <path>   Load a file or folder into shared context
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
from core.config       import MODELS
from core.mode_memory  import ModeMemorySession
from core.ui           import (
    mode_banner, status_line, divider,
    CYAN, YELLOW, GREEN, RED, PURPLE, DIM, BOLD, RESET, ok, warn, err, hi, lo
)


def _select_default_chat_model(models: list[dict], configured_model: str) -> str:
    names = [m.get("name", "") for m in models]
    if configured_model in names:
        return configured_model

    for name in names:
        lowered = name.lower()
        if "embed" not in lowered and "embedding" not in lowered:
            return name

    return configured_model or "mistral:latest"


def _store_chat_memory(sm: SessionManager, memory_session: ModeMemorySession, session: dict, ollama):
    sm.save(session)
    memory_session.store(ollama_client=ollama)


def _sync_chat_memory_session(memory_session: ModeMemorySession, session: dict):
    memory_session.session["name"] = session.get("name", memory_session.session["name"])
    memory_session.session["mode"] = session.get("mode", "chat")
    memory_session.session["model"] = session.get("model", "")
    memory_session.session["created"] = session.get("created", memory_session.session["created"])
    memory_session.session["updated"] = session.get("updated", memory_session.session["updated"])


HELP = f"""
{BOLD}Commands:{RESET}
  {YELLOW}/help{RESET}              Show this message
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

{BOLD}File context:{RESET}
  {YELLOW}/loadfile <path>{RESET}   Load a file or folder into shared context
  {YELLOW}/browse{RESET}            Pick a folder to load into context
  {YELLOW}/loaded{RESET}            Show loaded file context
  {YELLOW}/unload{RESET}            Clear loaded file context
"""


def run(initial_model: str = "", initial_session: str = None):
    """Entry point called by axio.py."""
    mode_banner("chat", "General-purpose conversational AI  |  Ollama + Claude")

    ollama = OllamaClient()
    sm     = SessionManager()
    logger = AuditLogger("chat")
    memory = ModeMemorySession("chat")

    # Try to init Claude (optional)
    try:
        claude    = ClaudeClient()
        claude_ok = True
        print(f"  Ollama: {ok('ONLINE ✓')}    Claude API: {ok('READY ✓')}\n")
    except Exception:
        claude    = None
        claude_ok = False
        print(f"  Ollama: {ok('ONLINE ✓')}    Claude API: {warn('OFFLINE')} {lo('(check .env)')}\n")

    # Resolve active model
    models = ollama.list_models()
    model  = initial_model or _select_default_chat_model(models, MODELS["chat"])

    # Init or resume session
    if initial_session:
        session = sm.load(initial_session) or sm.new(initial_session, model, "chat")
    else:
        session = sm.new(model=model, mode="chat")
    _sync_chat_memory_session(memory, session)

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

        # ── slash commands ────────────────────────────────────────
        memory_command = prompt[1:] if prompt.startswith("/memory") else prompt
        if memory.handle_command(memory_command):
            continue

        if prompt.startswith("/"):
            parts = prompt.split(maxsplit=1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts) > 1 else ""

            if cmd in ("/exit", "/quit"):
                _store_chat_memory(sm, memory, session, ollama)
                print(f"  {ok('Session saved.')} Goodbye.\n")
                break

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
                _store_chat_memory(sm, memory, session, ollama)
                session = sm.new(arg or None, session.get("model", model), "chat")
                memory = ModeMemorySession("chat")
                _sync_chat_memory_session(memory, session)
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
                        _store_chat_memory(sm, memory, session, ollama)
                        session = loaded
                        memory = ModeMemorySession("chat")
                        _sync_chat_memory_session(memory, session)
                        sname   = session["name"]
                        print(f"  {ok(f'Loaded: {sname}')}\n")
                    else:
                        print(f"  {err(f'Session not found: {arg}')}\n")
                else:
                    print(f"  {warn('Usage: /load <name>')}\n")

            elif cmd == "/save":
                _store_chat_memory(sm, memory, session, ollama)
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
            elif cmd == "/memory":
                memory.handle_command(("memory " + arg).strip())

            elif cmd == "/browse":
                print(SESSION_CONTEXT.load_browse_folder())

            elif cmd in ("/browse files", "/browsefiles"):
                print(SESSION_CONTEXT.load_browse_files())

            elif cmd == "/loadfile":
                if arg:
                    print(SESSION_CONTEXT.load_path(arg))
                else:
                    print(f"  {warn('Usage: /loadfile <file or folder path>')}\n")

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
            chat_prompt = SESSION_CONTEXT.inject(prompt, mode="block") if SESSION_CONTEXT.count else prompt
            memory_prefix = memory.prefix(prompt)
            if memory_prefix:
                chat_prompt = memory_prefix + "\n\n" + chat_prompt
            messages    = session["messages"] + [{"role": "user", "content": chat_prompt}]

            divider()
            response = ""

            if cur_backend == "claude":
                if not claude_ok:
                    print(f"  {err('Claude not available.')}\n")
                    continue
                print(f"\n  {PURPLE}[Claude]{RESET} ", end="", flush=True)
                response = claude.chat(messages, print_output=True)
            else:
                if not ollama.is_running():
                    print(f"  {err('Ollama is offline. Run: ollama serve')}\n")
                    continue
                print(f"\n  {CYAN}[{cur_model}]{RESET} ", end="", flush=True)
                try:
                    response = ollama.chat_stream(cur_model, messages)
                except Exception as e:
                    print(f"\n  {err(f'Error: {e}')}\n")
                    continue

            divider()
            print()

            sm.add_turn(session, prompt, response)
            memory.record_turn(prompt, response, model=cur_model, metadata={"backend": cur_backend})
            sm.save(session)
            logger.log_turn(prompt, response, cur_model, route=cur_backend)
