# GitHub workflow

Covers `github_status`, `github_pr_list`, `github_pr_view`, `git_branch`, `git_commit`, `github_push`, `github_fork`, `github_pr_create`, `github_pr_merge`. Backend: the `gh` CLI + `git`. Auth is the user's `gh auth login` — AXIO stores no credentials.

## Before you start
- Read the repo's `CONTRIBUTING.md` / `AGENTS.md` / `README` first; follow its branch naming, commit style, and PR conventions.
- `github_status` to confirm `gh` is authenticated and see the current branch and remotes. If it reports `gh not found`, tell the user to install GitHub CLI and run `gh auth login` — do not attempt a workaround.

## The standard flow (work on a repo like Claude Code / Codex)
1. `git_branch name="feature/short-topic"` — never commit straight to the default branch.
2. Make scoped changes with the filesystem tools.
3. Run the most direct verification (`run_npm_script test` / `run_python` / build), then `verification_gate`. `git_commit` records a mutation, so the gate must pass before the task can complete — **verify before you push**.
4. `git_commit message="clear, imperative summary"`.
5. `github_push branch="feature/short-topic"` — outward-facing, **requires approval**.
6. `github_pr_create title="…" body="what & why, verification run"` — outward-facing, **requires approval**. Set `base`/`head` when not the defaults; `draft: true` for work in progress.
7. Track it with `github_pr_list` / `github_pr_view`.

## No write access → fork first
- If you cannot push to the target repo, `github_fork` into the user's account (adds a remote), push the branch to the fork, then `github_pr_create` from the fork.

## Approval & safety
- Push, fork, PR-create, and PR-merge are `external` risk and **always** prompt for human approval. Declining returns `CANCELLED` and changes nothing.
- Never force-push a shared branch, rewrite published history, or merge a PR without an explicit request. Prefer `--squash` for merges unless the repo says otherwise.
- Keep secrets out of commits, branch names, PR titles, and bodies.
