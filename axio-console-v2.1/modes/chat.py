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
from core.ui           import (
    mode_banner, status_line, divider,
    CYAN, YELLOW, GREEN, RED, PURPLE, DIM, BOLD, RESET, ok, warn, err, hi, lo
)


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
"""


def run(initial_model: str = "", initial_session: str = None):
    """Entry point called by axio.py."""
    mode_banner("chat", "General-purpose conversational AI  |  Ollama + Claude")

    ollama = OllamaClient()
    sm     = SessionManager()
    logger = AuditLogger("chat")

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
    model  = initial_model or (models[0]["name"] if models else "mistral:latest")

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
            sm.save(session)
            print(f"\n  {ok('Session saved.')} Goodbye.\n")
            break

        if not prompt:
            continue

        # ── slash commands ────────────────────────────────────────
        if prompt.startswith("/"):
            parts = prompt.split(maxsplit=1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts) > 1 else ""

            if cmd in ("/exit", "/quit"):
                sm.save(session)
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
            chat_prompt = SESSION_CONTEXT.inject(prompt, mode="block") if SESSION_CONTEXT.count else prompt
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
            sm.save(session)
            logger.log_turn(prompt, response, cur_model, route=cur_backend)
