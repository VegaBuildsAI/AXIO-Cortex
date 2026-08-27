# Git evidence tools

Covers the read-only `git_status` and `git_diff`. (Branching, committing, pushing, and pull requests live in `github-workflow.md`.)

## Use
- `git_status` (short + branch) before and after a series of edits, to understand the current state and confirm what changed.
- `git_diff` to review changes before reporting or committing. Pass `paths` to keep the output bounded to the files you touched; use `staged: true` to review what is staged.
- These are read-only evidence tools — never shell out to `git` for a status/diff you can get here.

## Not every directory is a repo
- If the target is **not** a Git repository, `git_status`/`git_diff` return `ERROR: git exited 128` ("not a git repository"). This means **there is no repo here — continue the task without Git**. It is not a failure to recover from or retry; simply skip Git steps.
- Only include a `git_status` step in a plan when the target is plausibly a repository (a `.git` directory, a cloned project). Do not open with `git_status` reflexively on arbitrary folders.

## Error recovery
- `exit 128 / not a git repository` → no repo; proceed without Git (see above).
- Path errors → ensure `working_dir` is an absolute path to an existing directory.
