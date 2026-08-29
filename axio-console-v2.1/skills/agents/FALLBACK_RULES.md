# AXIO Fallback Rules (Plan Fase B · B5 / D)

How an agent hands off when it cannot finish a task. Two distinct mechanisms —
do not confuse them:

- **Fallback** = task hand-off *mediated by the orchestrator* when an agent
  cannot resolve something. Modeled by `harness/fallback.py`.
- **Peer call** = a direct, bounded sub-request *inside* one step (fetch this
  URL, read this file). The calling agent stays responsible for the result. The
  orchestrator only logs it. Governed by each agent's `peers` map.

## The AGENT_CANNOT_HANDLE protocol
An agent that cannot complete a task returns a structured signal instead of a
result:

```json
{ "status": "AGENT_CANNOT_HANDLE",
  "reason": "requires shell execution, not in my tools",
  "suggested_fallback": "RunAgent",
  "original_task": "create_dir('.instructions/...') failed" }
```

The orchestrator picks the next agent — the signal's `suggested_fallback` if it
names a real agent, otherwise the agent's declared `spec.fallback` — re-dispatches,
and counts hops.

## Defined chains
| From | To | When |
|------|----|----|
| FSAgent | RunAgent | write/create_dir keeps failing (e.g. path) → do it as a shell op |
| SearchAgent | WebAgent | datum not in the workspace → search the web |
| WebAgent | SearchAgent | internet down / repeated fetch timeout → local cache/workspace (bidirectional) |
| CtxAgent | WebAgent | context needs an external URL / image / API doc |
| TestAgent | RunAgent | runner misconfigured (not a real test failure) → run tests by hand |
| RunAgent | **USER** | RunAgent is the last resort for actions; on failure, escalate with full error |
| GitAgent | *(none)* | git ops are atomic — never delegated |
| PlanAgent | **USER** | planning failure escalates to the user |

## Hard limit
**Maximum 2 fallbacks per step.** After 2 hops without resolution, the
orchestrator **pauses the plan and asks the user**. No infinite loops. A spec
with `fallback = None` (RunAgent, GitAgent, PlanAgent) escalates to the user
immediately rather than chaining further.

## Logging
Every dispatch, fallback and escalation is logged to `logs/orchestrator.log`
with timestamp, step id, agent id and outcome (OK / FALLBACK / TIMEOUT / ESCALATE).
