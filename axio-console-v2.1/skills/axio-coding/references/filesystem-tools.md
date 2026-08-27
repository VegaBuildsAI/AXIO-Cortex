# Filesystem tools

Covers `read_file`, `write_file`, `edit_file`, `apply_patch`, `list_dir`, `create_dir`, `delete_file`, `search_files`, `grep_files`, `read_docx`.

## Reading & finding
- `read_file` before any edit — never edit text you have not just read. For large files, narrow with `grep_files`/`search_files` first, then read the relevant span.
- `search_files` finds paths by glob; use a narrow root and exclude generated/vendor trees. `grep_files` finds content; pass a file pattern to stay bounded.
- `list_dir` an unfamiliar destination before creating files in it.
- `read_docx` for local `.docx` — bounded, read-only. For a huge document, ask the user to point at the relevant section.

## Changing
- `edit_file` for a single surgical change: replace exact, previously read text. If the old text is not unique in the file, add surrounding context or use `apply_patch`.
- `apply_patch` for multiple changes in one file or coordinated changes across files — it validates every replacement and is atomic: if validation fails, nothing changes.
- `write_file` only when you own the whole file (new file, or full rewrite). Never use it to make a small change to a large file.
- `create_dir` before writing into a directory that does not exist.

## Safety
- `delete_file` is destructive: confirm the exact path and the user's intent first. Never delete to "clean up" unrelated files.
- Writes inside the active repo / loaded workspace roots run without a prompt; a write elsewhere is approval-gated. An absolute path alone does not authorize an unrelated location.

## Error recovery
- `read_file` "not found" → `list_dir` the parent to find the real name.
- `edit_file` "exact text not found" → `read_file` again to get current text (it may have changed) and retry with an exact match.
- `apply_patch` "validation failed" → re-read each affected file and adjust the patch anchors.
- `write_file` "ERROR" → `create_dir` the parent first.
