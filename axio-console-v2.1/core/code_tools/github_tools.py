"""GitHub / git-write toolset (gh CLI + git).

Lets the agent work on the user's repositories the way Claude Code / Codex do:
branch, commit, push, fork, and open/list pull requests. Read-only inspection
runs freely; local mutations set the verification-gate ``mutated`` flag; every
outward-facing action (push, fork, PR create/merge) is ``external`` risk and is
always human-gated by the registry. Authentication is delegated entirely to the
``gh`` CLI (`gh auth login`) — no credentials are stored by AXIO.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .registry import CodeTool, ToolResult

_GH_HINT = "Install GitHub CLI (https://cli.github.com) and run 'gh auth login'."


def _run(
    exe: str,
    arguments: list[str],
    working_dir: str,
    *,
    timeout: int = 60,
    max_chars: int = 50_000,
    hint: str = "",
) -> ToolResult:
    """Run ``exe`` with ``arguments`` inside an absolute ``working_dir``.

    Mirrors ``git_tools._git_run``: absolute-dir validation, binary discovery,
    ``shell=False`` argv, bounded timeout/output, and non-zero exit surfaced as
    an ``ERROR:`` ToolResult (so e.g. "not a git repository" is a clean signal).
    """
    root = Path(working_dir).expanduser()
    if not root.is_absolute():
        return ToolResult("ERROR: working_dir must be absolute", ok=False)
    root = root.resolve()
    if not root.is_dir():
        return ToolResult(f"ERROR: Working directory not found: {root}", ok=False)
    binary = shutil.which(exe)
    if not binary:
        extra = f" {hint}" if hint else ""
        return ToolResult(f"ERROR: {exe} executable not found.{extra}", ok=False)
    try:
        process = subprocess.run(
            [binary, *arguments],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, min(int(timeout), 300)),
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult(f"ERROR running {exe}: {exc}", ok=False)
    output = "\n".join(part.strip() for part in (process.stdout, process.stderr) if part.strip())
    if len(output) > max_chars:
        output = output[:max_chars] + f"\n... truncated at {max_chars} chars"
    if process.returncode:
        return ToolResult(f"ERROR: {exe} exited {process.returncode}\n{output}", ok=False)
    return ToolResult(output or "(no output)")


def _git(arguments: list[str], working_dir: str, **kwargs) -> ToolResult:
    return _run("git", arguments, working_dir, **kwargs)


def _gh(arguments: list[str], working_dir: str, **kwargs) -> ToolResult:
    return _run("gh", arguments, working_dir, hint=_GH_HINT, **kwargs)


# ── Read-only GitHub inspection (risk="read") ────────────────────────────────
def github_status(working_dir: str) -> ToolResult:
    auth = _gh(["auth", "status"], working_dir)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], working_dir)
    remote = _git(["remote", "-v"], working_dir)
    return ToolResult(
        "\n\n".join(
            [
                f"gh auth:\n{auth.content}",
                f"branch: {branch.content}",
                f"remotes:\n{remote.content}",
            ]
        )
    )


def github_pr_list(working_dir: str, state: str = "open", limit: int = 20) -> ToolResult:
    state = state if state in {"open", "closed", "merged", "all"} else "open"
    limit = max(1, min(int(limit), 100))
    return _gh(["pr", "list", "--state", state, "--limit", str(limit)], working_dir)


def github_pr_view(working_dir: str, number: str = "") -> ToolResult:
    args = ["pr", "view"]
    if str(number).strip():
        args.append(str(number).strip())
    return _gh(args, working_dir)


# ── Local git mutations (risk="write": sets the verification-gate mutated flag) ─
def git_branch(working_dir: str, name: str, create: bool = True) -> ToolResult:
    name = name.strip()
    if not name:
        return ToolResult("ERROR: branch name is required", ok=False)
    args = ["switch", "-c", name] if create else ["switch", name]
    return _git(args, working_dir)


def git_commit(working_dir: str, message: str, add_all: bool = True) -> ToolResult:
    message = message.strip()
    if not message:
        return ToolResult("ERROR: commit message is required", ok=False)
    if add_all:
        staged = _git(["add", "-A"], working_dir)
        if not staged.ok:
            return staged
    return _git(["commit", "-m", message], working_dir)


# ── Outward-facing actions (risk="external": always human-gated) ─────────────
def github_push(working_dir: str, branch: str = "", remote: str = "origin", set_upstream: bool = True) -> ToolResult:
    args = ["push"]
    branch = branch.strip()
    if branch:
        if set_upstream:
            args.append("-u")
        args.extend([remote.strip() or "origin", branch])
    return _git(args, working_dir, timeout=180)


def github_fork(working_dir: str, repo: str = "", add_remote: bool = True) -> ToolResult:
    args = ["repo", "fork"]
    if str(repo).strip():
        args.append(str(repo).strip())
    args.append("--remote" if add_remote else "--remote=false")
    return _gh(args, working_dir, timeout=180)


def github_pr_create(
    working_dir: str,
    title: str,
    body: str = "",
    base: str = "",
    head: str = "",
    draft: bool = False,
) -> ToolResult:
    title = title.strip()
    if not title:
        return ToolResult("ERROR: PR title is required", ok=False)
    args = ["pr", "create", "--title", title, "--body", body]
    if base.strip():
        args.extend(["--base", base.strip()])
    if head.strip():
        args.extend(["--head", head.strip()])
    if draft:
        args.append("--draft")
    return _gh(args, working_dir, timeout=180)


def github_pr_merge(working_dir: str, number: str, method: str = "squash") -> ToolResult:
    number = str(number).strip()
    if not number:
        return ToolResult("ERROR: PR number is required", ok=False)
    method = method if method in {"squash", "merge", "rebase"} else "squash"
    return _gh(["pr", "merge", number, f"--{method}"], working_dir, timeout=180)


_WORKDIR = {"working_dir": {"type": "string"}}

TOOLS = [
    CodeTool(
        "github_status",
        "Report gh auth status, current branch, and remotes for a repository. Read-only.",
        {"type": "object", "properties": {**_WORKDIR}, "required": ["working_dir"]},
        github_status,
        "read",
    ),
    CodeTool(
        "github_pr_list",
        "List pull requests for the repository via gh. Read-only.",
        {"type": "object", "properties": {**_WORKDIR, "state": {"type": "string", "enum": ["open", "closed", "merged", "all"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["working_dir"]},
        github_pr_list,
        "read",
    ),
    CodeTool(
        "github_pr_view",
        "View one pull request (by number, or the current branch's PR) via gh. Read-only.",
        {"type": "object", "properties": {**_WORKDIR, "number": {"type": "string"}}, "required": ["working_dir"]},
        github_pr_view,
        "read",
    ),
    CodeTool(
        "git_branch",
        "Create or switch to a local Git branch.",
        {"type": "object", "properties": {**_WORKDIR, "name": {"type": "string"}, "create": {"type": "boolean"}}, "required": ["working_dir", "name"]},
        git_branch,
        "write",
    ),
    CodeTool(
        "git_commit",
        "Stage all changes and create a Git commit with a message. Records a mutation for the verification gate.",
        {"type": "object", "properties": {**_WORKDIR, "message": {"type": "string"}, "add_all": {"type": "boolean"}}, "required": ["working_dir", "message"]},
        git_commit,
        "write",
    ),
    CodeTool(
        "github_push",
        "Push commits to the GitHub remote. Outward-facing; requires human approval.",
        {"type": "object", "properties": {**_WORKDIR, "branch": {"type": "string"}, "remote": {"type": "string"}, "set_upstream": {"type": "boolean"}}, "required": ["working_dir"]},
        github_push,
        "external",
    ),
    CodeTool(
        "github_fork",
        "Fork a GitHub repository into the user's account via gh. Outward-facing; requires human approval.",
        {"type": "object", "properties": {**_WORKDIR, "repo": {"type": "string"}, "add_remote": {"type": "boolean"}}, "required": ["working_dir"]},
        github_fork,
        "external",
    ),
    CodeTool(
        "github_pr_create",
        "Open a pull request via gh with a title and body. Outward-facing; requires human approval.",
        {"type": "object", "properties": {**_WORKDIR, "title": {"type": "string"}, "body": {"type": "string"}, "base": {"type": "string"}, "head": {"type": "string"}, "draft": {"type": "boolean"}}, "required": ["working_dir", "title"]},
        github_pr_create,
        "external",
    ),
    CodeTool(
        "github_pr_merge",
        "Merge a pull request via gh (squash by default). Outward-facing; requires human approval.",
        {"type": "object", "properties": {**_WORKDIR, "number": {"type": "string"}, "method": {"type": "string", "enum": ["squash", "merge", "rebase"]}}, "required": ["working_dir", "number"]},
        github_pr_merge,
        "external",
    ),
]
