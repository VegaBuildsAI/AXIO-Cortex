# Python runtime and installed capabilities

## Interpreter selection

Use `inspect_python_environment` before selecting imports or commands. AXIO resolves Python in this order: target workspace `.venv`, AXIO Console `.venv`, then the interpreter running AXIO. Invoke that exact executable; activation is optional and must not be assumed.

Use `run_python` for existing `.py` files. It executes an argument list with `shell=False`, bounds runtime, captures stdout/stderr, and asks the user before code runs. Never place keys, tokens, passwords, PHI, or account identifiers in command arguments.

## Environment rules

- Treat virtual environments as disposable, isolated dependency containers. Do not commit or relocate them.
- Use `python -m pip` with the selected interpreter so installation and execution target the same environment.
- Inspect `pyproject.toml`, `requirements.txt`, lockfiles, and actual imports before adding a dependency.
- Package distribution names and import names are not guaranteed to match. Use `importlib.metadata` rather than guessing.
- Prefer standard-library `unittest` when that is the repository convention. Use pytest only when declared/installed; it is not part of the AXIO Console direct requirements as of this snapshot.
- On Windows, use `npm.cmd` when PowerShell execution policy blocks `npm.ps1`.

## Verified AXIO Console environment snapshot

The project `.venv` was inspected on 2026-08-24 with Python 3.12.13. Core direct capabilities found: Anthropic SDK, FastAPI/Uvicorn, Pydantic and pydantic-settings, Requests/HTTPX/aiohttp, ChromaDB, Psycopg 3 + pgvector, NumPy, PyYAML, Rich, Typer/Click, Tenacity, OpenTelemetry, WebSockets, Kubernetes client, and Hugging Face/tokenizers/ONNX Runtime dependencies.

This is not an authorization to import all of them and not a guarantee about another workspace. Call `inspect_python_environment` for the live full distribution list. The checked-in full snapshot is `python-packages-2026-08-24.md` in this reference directory.

## Verification ladder

1. Syntax/import check for changed modules.
2. Focused unit test or executable reproducer for the changed behavior.
3. Related test module or service health check.
4. Full suite/build only when scope and runtime cost justify it.
5. Live external integration only with required credentials, network, service state, and authorization.

Static parsing, mocked tests, and successful imports do not prove a live database, model API, browser UI, deployment, or external service works.
