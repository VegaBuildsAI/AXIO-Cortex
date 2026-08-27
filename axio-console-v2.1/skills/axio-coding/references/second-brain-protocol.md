# Second Brain protocol for AXIO Code

Canonical vault: `C:\Users\AXIO\Documents\Second Brain`.

The legacy OneDrive Obsidian Vault is read-only and must never receive new memory. The Second Brain contains mixed-sensitivity knowledge, so AXIO Code must not automatically inject the raw vault into a cloud-model prompt.

## Routing

When the user explicitly asks to use the Second Brain or a task depends on prior AXIO decisions:

1. Read `MEMORY.md` to locate the relevant note.
2. Read `Memory\claude\preferences.md` for working style.
3. Read `Memory\codex\codex-work-index.md` for prior verified work.
4. Read `Memory\shared\project-file-registry.md` for project-to-code mappings.
5. Open only the small set of notes those indexes point to. Do not scan the whole vault.

## Privacy and provenance

- Do not send secrets, raw personal records, PHI, full identifiers, contracts, or unrelated notes to a cloud model.
- Distill only the technical facts needed for the active task and label historical evidence as potentially stale until reverified.
- Treat Second Brain paths and stubs as routing hints, not proof that a repository, deployment, service, or file currently exists.
- Do not write, move, rename, or synchronize vault content unless the user explicitly requests a Second Brain update.
- When writing is authorized, update the existing canonical note rather than duplicating it; preserve PARA structure, frontmatter, and wikilinks.

This skill contains a curated snapshot so ordinary Code tasks receive the AXIO engineering pattern without exposing the full vault.
