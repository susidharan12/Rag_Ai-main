# Bonus: AgentCard and A2A lifecycle mapping (design only, not implemented)

**AgentCard:** `agent_card.json` (two skills, `text/plain` in and out, bearer auth).

## The failed case (eval_014, version worker returns 500) on the A2A task lifecycle

What the orchestrator actually did: `submitted` -> `working` -> retry -> returned the code sample with a `[PARTIAL ANSWER]` notice in the text, which an A2A client would see as **`completed`**. The degradation is hidden inside prose.

What it should have done: end in **`input-required`**, not `failed`. The question named no SDK version, the version check is the only thing that could resolve one, and it is down. Emit a status message "Version check unavailable. Are you on SDK v2 or v3?", attach the unverified v3 sample as a partial artifact, and resume to `completed` once the developer answers. `failed` would throw away a useful answer. `completed` would hide that the answer was unverified, which is what the current prose caveat does.

When the question does state a version (e.g. eval_023) the same 500 would be `failed`, because no input from the developer could fix it.

## What A2A buys over a plain REST call to the worker (2 lines)

A REST call gives the orchestrator an HTTP status it must interpret itself; A2A gives a typed task state (`failed`, `input-required`, `auth-required`) that any client can act on without knowing our internals.
The AgentCard also lets a caller discover the skills, input modes and auth up front, so workers can be swapped or run by another team without changing the orchestrator.
