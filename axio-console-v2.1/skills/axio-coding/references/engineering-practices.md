# Engineering practices for AXIO Code

Apply these conventions only after reading the repository's own instructions and established style. Live project evidence wins over generic patterns.

## Design

- Prefer the smallest cohesive change that satisfies the request; avoid speculative abstractions.
- Preserve public APIs and existing path/config contracts unless the task explicitly changes them.
- Keep configuration in the project's source of truth and credentials in environment variables or the existing secret mechanism.
- Use specific exceptions and actionable failures. Do not swallow errors with a bare `except`.
- Add idempotency where retries can repeat writes or external effects.

## Python

- Select the interpreter with `inspect_python_environment` before relying on packages or syntax versions.
- Use `pathlib` for Windows paths and structured argument lists with `shell=False` for subprocesses.
- Follow the project's typing, formatting, and test conventions; do not impose a new project layout on an established repository.
- For FastAPI/Pydantic behavior, verify installed versions before using version-sensitive configuration, validators, or test clients.

## APIs and data

- Validate inputs at trust boundaries and return errors without leaking internal details or credentials.
- Parameterize SQL and preserve transaction boundaries.
- Distinguish authentication, authorization, validation, conflict, and server failures rather than flattening them into one response.
- Add migrations and rollback/recovery reasoning when persistent schemas change.

## Verification

- Diagnose with the narrowest reproduction first.
- Test behavior and failure paths, not merely file existence or generated wording.
- Run focused checks before broader suites; record only successful executable checks as completion evidence.
- Treat warnings separately from failures and report both honestly.

## Security

- Never hardcode or print API keys, passwords, recovery codes, tokens, or full environment files.
- Never evaluate untrusted input or interpolate it into shell/SQL commands.
- Inspect Git diff before completion so unrelated or secret-bearing changes are not accidentally included.
- Deployment, publishing, commits, external APIs, and destructive cleanup require the authorization defined by the runtime and the user's scope.
