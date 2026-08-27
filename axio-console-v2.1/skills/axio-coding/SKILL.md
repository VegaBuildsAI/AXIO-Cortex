---
name: axio-coding
description: Build, plan, diagnose, and verify AXIO software with its local-first Windows runtime, shared Code tools, human gates, and evidence-backed engineering conventions.
metadata:
  always_apply: true
  triggers: [python, fastapi, api, code, debug, test, postgres, pgvector, chroma, ollama, react, nextjs, cloudflare, mcp]
---

# AXIO coding workflow

Start from the active repository, its instructions, dependency files, runtime, and current Git state. AXIO knowledge informs decisions but never overrides live project evidence.

Use the smallest relevant reference:

- For architecture, product stack, memory, routing, privacy, or cross-project conventions, read `{{SKILL_ROOT}}\references\axio-stack.md`.
- For Python execution, environment selection, installed libraries, testing, and safe subprocess usage, read `{{SKILL_ROOT}}\references\python-runtime.md`.
- For Node/npm inspection, package scripts, builds, and JavaScript verification, read `{{SKILL_ROOT}}\references\node-runtime.md`.
- For local-model limitations, Plan Mode, and safe execution sequencing, read `{{SKILL_ROOT}}\references\local-model-planning.md`.
- For Python/API/testing/security engineering conventions, read `{{SKILL_ROOT}}\references\engineering-practices.md` only when that domain is relevant.
- For choosing and sequencing Code tools, read `{{SKILL_ROOT}}\references\tool-routing.md`.
- For file read/write/edit/patch/list/search and DOCX, read `{{SKILL_ROOT}}\references\filesystem-tools.md`.
- For read-only Git status/diff (including the "not a repo" case), read `{{SKILL_ROOT}}\references\git-tools.md`.
- For web research (`web_search`/`web_fetch`/`web_extract`) and the evidence workflow, read `{{SKILL_ROOT}}\references\web-tools.md`.
- For the headless browser tools, read `{{SKILL_ROOT}}\references\browser-tools.md`.
- For workspace indexing, semantic search, and library-doc lookup, read `{{SKILL_ROOT}}\references\retrieval-tools.md`.
- For scaffolding projects/modules, read `{{SKILL_ROOT}}\references\scaffold-tools.md`.
- For the verification gate, `run_command`, and recovering from failed builds/tests, read `{{SKILL_ROOT}}\references\verification-and-recovery.md`.
- For working on GitHub repos (branch, commit, push, fork, pull requests) with the `gh` CLI, read `{{SKILL_ROOT}}\references\github-workflow.md`.
- For Second Brain routing, provenance, and privacy boundaries, read `{{SKILL_ROOT}}\references\second-brain-protocol.md`.
- For version-sensitive APIs, read `{{SKILL_ROOT}}\references\official-docs.md` and verify the installed version with `inspect_python_environment`.

## Tool index (every tool has a reference)

The runtime also loads `{{SKILL_ROOT}}\tool-calling-skills.yaml`, which contains one compact,
model-visible calling skill for each registered tool. Registry/catalog parity is
validated by tests; adding or removing a tool requires updating that catalog.

- Filesystem — read_file, write_file, edit_file, apply_patch, list_dir, create_dir, delete_file, search_files, grep_files, read_docx → `filesystem-tools.md`
- Artifacts — create_docx, create_xlsx, create_pptx, create_pdf → model-visible cards in `tool-calling-skills.yaml`
- Python — inspect_python_environment, run_python → `python-runtime.md`
- Node — inspect_node_environment, run_npm_script → `node-runtime.md`
- Git (read) — git_status, git_diff → `git-tools.md`
- GitHub — github_status, github_pr_list, github_pr_view, git_branch, git_commit, github_push, github_fork, github_pr_create, github_pr_merge → `github-workflow.md`
- Web — web_search, web_fetch, web_extract → `web-tools.md`
- Browser — browser_open, browser_snapshot, browser_click → `browser-tools.md`
- Retrieval — index_workspace, semantic_search, search_docs → `retrieval-tools.md`
- Scaffold — scaffold_project, scaffold_module → `scaffold-tools.md`
- Verification & shell — verification_gate, run_command → `verification-and-recovery.md`

Task progress is tracked by the `verification_gate` state machine, not a `task_update` tool (there is none): after a successful mutation, run a check and call `verification_gate` before `TASK_COMPLETE`.

## Non-negotiable AXIO invariants

- Local-first: keep sensitive data and embeddings local unless the user explicitly authorizes a cloud path.
- Human gate: consequential actions are drafted and verified before an explicit approval step.
- Config-driven: use the project's configuration source of truth; do not scatter model names, paths, limits, or secrets.
- Honest state: distinguish verified runtime evidence, historical evidence, inference, plan, stub, and unimplemented behavior.
- Durable systems: use atomic persistence, idempotent replay where retries occur, bounded loops/timeouts, structured audit logs, and explicit failure states.
- Preserve boundaries: inspect nested roots and path contracts; do not relocate runtime files or rewrite unrelated work.

## Execution loop

1. Discover instructions, roots, dependencies, tests, and worktree state.
2. State the working hypothesis internally and choose the narrowest tools that can prove or change it.
3. Make scoped changes, preserving established style and APIs.
4. Run the most direct verification available, then broader tests only when justified.
5. After any successful mutation, call `verification_gate` with the required checks. Do not emit `TASK_COMPLETE` unless it passes.
6. Report observed results. Never convert a plan, static check, or historical note into a live-success claim.
