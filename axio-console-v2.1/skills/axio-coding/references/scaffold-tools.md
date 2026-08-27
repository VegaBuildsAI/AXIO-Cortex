# Scaffold tools

Covers `scaffold_project`, `scaffold_module`.

## Rules
- `scaffold_project` creates a new project from an approved AXIO template. It **never overwrites** an existing destination — `list_dir` the destination first to confirm it does not exist; use an absolute path.
- `scaffold_module` creates a standard module (Python / FastAPI-domain / React) inside an existing project. It **never overwrites** existing files — `list_dir` the parent first to see the current structure.
- Use these only for a requested standard structure. After scaffolding, inspect and verify the generated output before reporting completion.

## Error recovery
- "destination exists" → choose a different destination, or (with the user's intent) work inside the existing one with the filesystem tools instead.
- Unknown template/module type → list the available templates/types before retrying.
