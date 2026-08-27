# AXIO Code tool routing

Choose the narrowest tool that produces observable evidence.

| Need | Tool | Key rule |
|---|---|---|
| Read a known text file | `read_file` | Read before editing; large files require targeted search. |
| Find paths | `search_files` | Use a narrow root and glob; exclude generated/vendor trees. |
| Find code/text | `grep_files` | Search before broad reads; use a file pattern. |
| Inspect a directory | `list_dir` | Required before creating files in an unfamiliar destination. |
| Make a precise change | `edit_file` | Replace exact, previously read text; preserve unrelated edits. |
| Make coordinated exact changes | `apply_patch` | Validate every replacement before writing; use for multi-file edits. |
| Create/replace content | `write_file` | Use only when full-file ownership is clear. |
| Create a directory | `create_dir` | Confirm the parent and intended root first. |
| Delete a file | `delete_file` | Destructive; verify the exact file and user intent first. |
| Inspect Python | `inspect_python_environment` | Read-only; call before relying on a package or interpreter. |
| Execute a Python file | `run_python` | Structured args, no shell interpolation, timeout, human approval. |
| Inspect Node/npm | `inspect_node_environment` | Read scripts, versions, locks, and dependency state before npm work. |
| Run a package script | `run_npm_script` | Only declared scripts; structured args, timeout, human approval. |
| Inspect Git state | `git_status`, `git_diff` | Read-only evidence; never use shell for these common checks. |
| Inspect GitHub auth/PRs | `github_status`, `github_pr_list`, `github_pr_view` | Read-only `gh` context; no approval needed. |
| Branch / commit locally | `git_branch`, `git_commit` | Local mutations; `git_commit` records a mutation so the gate fires before push. |
| Push / fork / open or merge PR | `github_push`, `github_fork`, `github_pr_create`, `github_pr_merge` | Outward-facing; always human-approved. Verify before pushing. See `github-workflow.md`. |
| Read Word text | `read_docx` | Local, bounded, read-only DOCX extraction. |
| Discover public URLs | `web_search` | SearXNG-backed structured discovery; this is not page retrieval. |
| Fetch a known page | `web_fetch` | Public HTTP(S) GET only; SSRF, redirect, type, byte, and timeout limits. |
| Clean fetched HTML | `web_extract` | Use the cache id from `web_fetch`; do not send raw HTML to the model. |
| Render a JavaScript page | `browser_open`, `browser_snapshot` | Headless and read-only; private networks, files, downloads, uploads, and forms are blocked. |
| Click a safe page control | `browser_click` | Only snapshot refs for links/non-submit buttons; requires approval. |
| Build local code retrieval | `index_workspace` | Derived FTS5 + local embedding cache; it does not modify source files. |
| Find code by concept | `semantic_search` | Index first; returns bounded path and line-addressable chunks. |
| Find official library docs | `search_docs` | Prefer cached official sources; refresh through SearXNG when available. |
| Create a standard project | `scaffold_project` | Approved template, absolute destination, atomic creation, never overwrite. |
| Create a standard module | `scaffold_module` | Approved module type inside an existing absolute parent. |
| Verify completion | `verification_gate` | Required after mutations; it accepts only successful recorded checks. |
| Services, package install, or shell-native fallback | `run_command` | Human approval; use a verified working directory and bounded command. |

## Sequencing patterns

- Diagnose: search -> read -> inspect runtime -> reproduce -> explain. Do not edit unless asked.
- Change: inspect instructions/status -> search/read -> edit/write -> focused verification -> `verification_gate` -> report.
- Python dependency: inspect environment -> read dependency manifest -> verify official versioned API -> edit -> focused import/test.
- Database change: inspect schema/migrations -> plan transaction/idempotency -> implement -> run isolated tests -> request approval before live mutation.
- External integration: verify configured client/tool exists -> inspect permissions and secrets without printing them -> run a safe health/read call -> require a gate before mutation.

The listed tools are the tools AXIO Code actually exposes. Web search requires the configured SearXNG service; browser tools require Playwright plus Chromium. Do not claim either layer is live until its runtime check succeeds. Do not claim authenticated GUI, MCP, Docker, Cloudflare, GitHub, upload, download, or form-submit access unless a separate active runtime explicitly provides and verifies it. Use `run_command` only when a corresponding CLI is present and the user approves execution.

Writes under the active repository or a loaded file's parent run without an extra gate. A write elsewhere requires explicit approval. This boundary does not authorize unrelated files merely because their paths are absolute.
