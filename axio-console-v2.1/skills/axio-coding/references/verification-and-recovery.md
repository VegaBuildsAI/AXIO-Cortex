# Verification & error recovery

Covers `verification_gate`, `run_command`, and how to respond when checks fail.

## The gate
- After any successful `write`/`destructive` mutation, run the most direct executable check (tests, build, or a run) and then call `verification_gate`.
- The gate blocks `TASK_COMPLETE` while code has been mutated but no successful test/build/verification is recorded. `TASK_COMPLETE` is allowed only after the gate returns `VERIFICATION PASSED`.
- A file read-back proves persistence only — it is **not** verification. Tests, builds, lint, or behavioral runs are.

## When a build or test FAILS (do not thrash)
This is the common failure mode. When `run_npm_script build`/`test` or `run_python` exits non-zero:
1. **Read the actual stderr/first error.** Fix the root cause (a real bug, a missing dep, a wrong path).
2. **Do not invent exotic runtime workarounds** to force a green result — e.g. ad-hoc `ts-node`, `node --experimental-strip-types`, piping a TS file into node, or swapping the declared script for a hand-rolled command. If a project's own `build`/`test`/`verify` script fails, the fix is in the code or config, not a different invocation.
3. **If the failure is outside the task's scope** (a pre-existing broken build, a missing external service), stop and **report honestly**: what you changed, what check failed, the exact error, and what is needed. Do not mark the task complete, and do not claim a success you did not observe.
4. Retry at most twice, each time with a specific diagnosis — never blind retries.

## run_command
- Last resort, only when no dedicated tool covers the operation (services, `pip install`, `git`/`gh` when a dedicated tool does not apply). Requires human approval.
- Use a verified absolute working directory and a bounded command. Show the real output; never fabricate it.
- Prefer the dedicated tools: `run_python`, `run_npm_script`, `git_status`/`git_diff`, and the GitHub tools over free-form `run_command`.

## Never mark completed if
- a write/patch returned `ERROR:`, or `verification_gate` did not pass, or a `run_*` tool returned a non-zero exit. Report the failure instead.
