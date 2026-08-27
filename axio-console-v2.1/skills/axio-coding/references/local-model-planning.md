# Local Code planning and execution

AXIO Code uses the same maintained prompt, 29-tool registry, risk policy, audit path, and verification gate for both Claude and local Ollama models. Do not create a second tool schema or implementation for a particular model.

## Plan Mode

Use `plan <task>` when the user wants review before execution or when a multi-file change benefits from an explicit sequence. Planning is read-only: it must not call tools, edit files, run commands, or imply approval.

A useful plan:

- has at most 15 numbered steps;
- names one real registered tool per step when a tool is needed;
- starts with repository and instruction discovery;
- places execution checks after the relevant changes;
- ends with `verification_gate` after successful test/build evidence;
- identifies any destructive or external step as requiring its runtime gate.

`execute` runs only the last plan explicitly approved in the current Code session. Approval of the plan does not pre-authorize execute, destructive, external, deployment, or credentialed operations; their normal gates still apply.

## Local model discipline

- Prefer short observations and one coherent action at a time; inspect results before deciding the next action.
- Use the dedicated tool instead of asking PowerShell to duplicate filesystem, Python, npm, Git, or DOCX behavior.
- Do not claim a model capability or context limit from memory. Trust `core/config.py`, the live Ollama inventory, and actual tool results.
- A file read-back proves persistence, not correctness. Verification requires an applicable successful Python, npm, build, lint, or test execution followed by `verification_gate`.
- If the local model repeatedly narrates without acting or cannot satisfy the gate within the bounded loop, stop honestly. Do not fabricate completion or silently route to cloud while `LOCAL_ONLY=1`.

## Vision

The `vision <absolute-image-path>` session command may attach a local image to subsequent Ollama requests. It is context input, not a filesystem or execution tool. Never infer permission to transmit it to a cloud backend.
