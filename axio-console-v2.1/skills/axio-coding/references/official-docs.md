# Official documentation routes

Use these primary sources for version-sensitive implementation details. Confirm the installed version first.

- Python 3.12 `venv`: https://docs.python.org/3.12/library/venv.html
- Python 3.12 `importlib.metadata`: https://docs.python.org/3.12/library/importlib.metadata.html
- Python `subprocess` security: https://docs.python.org/3/library/subprocess.html#security-considerations
- Python `pathlib`: https://docs.python.org/3.12/library/pathlib.html
- Python `unittest`: https://docs.python.org/3.12/library/unittest.html
- Python Packaging User Guide: https://packaging.python.org/en/latest/guides/
- FastAPI tutorial and testing: https://fastapi.tiangolo.com/tutorial/ and https://fastapi.tiangolo.com/tutorial/testing/
- Pydantic models and settings: https://docs.pydantic.dev/latest/concepts/models/ and https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- Psycopg 3 usage and transactions: https://www.psycopg.org/psycopg3/docs/basic/usage.html and https://www.psycopg.org/psycopg3/docs/basic/transactions.html
- pgvector Python: https://github.com/pgvector/pgvector-python
- Chroma collections and embeddings: https://docs.trychroma.com/docs/collections/manage-collections and https://docs.trychroma.com/docs/embeddings/embedding-functions
- Anthropic tool use: https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview
- Ollama tool calling: https://docs.ollama.com/capabilities/tool-calling
- Ollama embeddings API: https://docs.ollama.com/api/embed
- Playwright Python library and Page routing: https://playwright.dev/python/docs/library and https://playwright.dev/python/docs/api/class-page#page-route
- SearXNG settings and Search API: https://docs.searxng.org/admin/settings/settings.html and https://docs.searxng.org/dev/search_api.html
- Requests: https://requests.readthedocs.io/en/latest/
- HTTPX: https://www.python-httpx.org/
- Uvicorn settings: https://www.uvicorn.org/settings/
- PyYAML: https://pyyaml.org/wiki/PyYAMLDocumentation

## Operational consequences

- A venv owns its interpreter and site-packages; use that interpreter explicitly.
- Distribution metadata is authoritative for installed names/versions, but distribution and import names can differ.
- Argument-list subprocess calls avoid implicit shell parsing. When a shell is explicitly invoked, quoting and metacharacters become the caller's responsibility.
- FastAPI's `TestClient` uses HTTPX and can test the ASGI app without a live socket; it does not prove external services are reachable.
- Pydantic validates the resulting model shape and may coerce input unless strict behavior is configured.
- Psycopg starts transactions implicitly by default; use context managers and explicit transaction boundaries to avoid idle or silently rolled-back work.
- Claude and Ollama client tools require a complete loop: provide schemas, execute requested tools client-side, return matching tool results, then continue the model turn.
- Ollama embeddings accept batched inputs; use the same local embedding model for indexing and querying.
- Playwright browser packages and browser binaries are separate installations. Browser request routing must block private/file destinations before navigation or interaction.
- SearXNG JSON output must be explicitly enabled in the instance configuration; an unavailable or HTML-only endpoint is not a working search API.
