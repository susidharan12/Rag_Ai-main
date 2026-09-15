# Week 7 · Module 4 · Agents — Developer Documentation Agent (Task Set E)

> A hand-built ReAct agent with visible steps and strict circuit breakers,
> raced against a fixed, hard-coded workflow that calls the *same tools* on
> **real** developer documentation, with a real LLM (Groq) behind both —
> speed, cost, and pass rate, not vibes.

---

## Deliverables (submission checklist)

| Requirement | Where |
|---|---|
| Agent and workflow, each runnable by one command | `python -m week7_agent.race` runs both; see "Run it yourself" |
| `race.csv` / table, 8 numbers over the same 10 questions | `week7_agent/race.csv` (regenerated every run) |
| Log excerpt of a budget-triggered termination | `week7_agent/budget_termination_log.txt` (regenerate with `python -m week7_agent.budget_termination_demo`) |
| Diff of the third tool's description + enum | `week7_agent/third_tool_diff.md` |
| Verdict paragraph naming the dependency question class | [Verdict](#verdict) below (auto-generated into `race_results.json["recommendation"]`, <150 words) |

---

## The third tool: `check_deprecation`

Added to `rag_core/agent.py` alongside the existing `search_docs` /
`get_version_info` / `compare_versions` / `get_error_info` /
`get_parameter_default` tools. One job: *given a subject you already
identified and a target `api_version`, was it removed/changed, and what
replaced it?* `api_version` is a closed Pydantic `Enum`
(`2022-11-28` / `2025-06-01` / `2.x` / `3.x`), not a free string like
`get_version_info.version` — a hallucinated version is rejected as a schema
error before it ever reaches retrieval. Full before/after diff:
**`week7_agent/third_tool_diff.md`**.

---

## The agent loop (`rag_core/agent.py`)

```
THOUGHT   — "explain why this step"           (Chain of Thought)
ACTION    — pick a tool + arguments
OBSERVE   — read the tool's result
REPEAT    — until the agent says finish, or a circuit breaker trips
```

### Tools (strict, type-safe Pydantic schemas)

| Tool | Purpose |
|---|---|
| `search_docs(query)` | Vector search over the indexed docs |
| `get_version_info(version, query)` | Docs scoped to one named version |
| `compare_versions(query)` | Two versions' chunks side by side |
| `get_error_info(code, query)` | Error-code / retryability lookups |
| `get_parameter_default(param, query)` | Parameter default/type/description |
| **`check_deprecation(subject, api_version)`** | **New (Task Set E).** Did `subject` change/get replaced at `api_version`, and by what? `api_version` is an enum. |
| `finish(answer)` | End the loop with the final answer |

A malformed call never crashes the loop — it becomes a "Tool call
rejected: ..." observation, and 2 consecutive rejections trip the
`schema_error` circuit breaker.

A real `GROQ_API_KEY` **is** configured for this project (in `.env`,
gitignored) — both the agent's tool-selection and the workflow's final
generation step run through Groq's `openai/gpt-oss-120b`, not a
deterministic stand-in. When no key is configured, `_fallback_plan` is a
genuinely conditional rule-based planner (documented in git history) that
exercises the same tool-selection logic without an LLM.

### Circuit breakers (all 4 required budgets, enforced in `run_agent`)

| Condition | Default | `stopped_by` |
|---|---|---|
| `max_steps` | 5 (race uses 4 — see rate-limit note below) | `"max_steps"` |
| `time_budget` | 30 s | `"time_budget"` |
| `max_tokens` | 6000 | `"token_budget"` |
| `max_cost_usd` | $0.01 | `"cost_budget"` |
| 2 consecutive schema failures | — | `"schema_error"` |
| `finish` tool / parse failure | — | `"finished"` / `"parse_error"` |

**Proof all four fire cleanly:** `python -m week7_agent.budget_termination_demo`
forces each budget low enough to trip it on a real question against the
real corpus and a real LLM call, and logs `stopped_by` + a real (possibly
partial) answer for each — no exception, no infinite loop. Log:
`week7_agent/budget_termination_log.txt`. One of the demo's runs actually
tripped `time_budget` organically, not by design — a Groq rate-limit
backoff (see below) pushed a normal-budget call past 30s, which is exactly
the kind of real-world slow-API case this breaker exists for.

---

## The fixed workflow (`rag_core/workflow.py`)

Task Set E requirement: *"same tools, same model, same output contract, no
loop."* This is **not** a different, simpler retrieval path — it calls the
exact same `rag_core.agent._execute_tool` functions the agent uses, always
in this order, for every question:

1. `search_docs(question)` — find the relevant docs page(s)
2. `get_version_info(target_version, question)` — read the spec scoped to
   the target version (deterministically parsed from the question text,
   with a hard-coded default when none is named)
3. `check_deprecation(subject, target_version)` — **always** runs, even
   when the question doesn't need it. That's the point of comparison: the
   agent can skip this step when nothing changed; the fixed workflow never
   does.
4. Generate the final answer from everything steps 1–3 retrieved, via the
   same generator (`settings.DEFAULT_GENERATOR` — Groq when configured,
   otherwise the deterministic extractive fallback) the agent's own answer
   synthesis uses.

No branching on which tool to call next — only the *values* (which version,
which subject) are input-dependent, which is normal data flow through a
fixed pipeline, not a decision loop.

---

## The race (`week7_agent/race.py`)

Runs both systems on the same **10 real migration scenarios** (the first 10
non-negative cases in `golden_sets/gs_hard.json`) — real "compare/migrate X
between API versions" questions against the real GitHub REST API and
Swagger Codegen v2/v3 reference PDFs in `corpus/dev_docs/`.

**4 of the 10 (`H01`, `H04`, `H06`, `H08`) are step-3-depends-on-step-2
cases** — the golden answer is explicitly framed as "old behavior
removed/replaced by new behavior" (e.g. H06: `make_latest` *replaces* an
undocumented heuristic outright), not just "a new option was added". The
race reports, per run, how many of these 4 the agent actually resolved by
calling `check_deprecation`.

Scoring is golden-answer-derived: `_extract_key_tokens()` pulls the
quoted values/flags/numbers out of each golden answer, and a produced
answer **passes** when ≥60% of those tokens appear in it.

### Latest real result (`race_results.json` / `race.csv`) — real Groq LLM

| Metric | Agent (ReAct) | Fixed Workflow |
|---|---|---|
| Pass rate | 60% (6/10) | 60% (6/10) |
| p50 latency | ~7-20s | ~20-22s |
| Total est. tokens | ~20,000 | ~33,000 |
| Est. cost (10 questions) | ~$0.005 | ~$0.004 |

Re-run `python -m week7_agent.race` to regenerate both files. **These
numbers move more than a deterministic system's would** — see the
rate-limit caveat below before reading anything into small swings.

### Bugs found and fixed getting a real LLM working (this is the actual finding)

Wiring up a real `GROQ_API_KEY` for this deliverable surfaced five
concrete, previously-invisible bugs — each one made the "quality" numbers
look worse than the system actually was, for reasons that had nothing to
do with retrieval or prompt quality:

1. **Scorer bugs inflated/deflated pass rate independent of answer
   quality.** `_extract_key_tokens()`'s quote-matching regex treated
   possessive apostrophes ("repository's") as opening quotes, sometimes
   capturing a 60-character run-on sentence fragment as one "required
   fact" that could never realistically match (H06), while a golden answer
   with zero quoted/numeric facts (H02, whose key facts are `!pattern`
   examples, never quoted) could never pass *regardless of answer
   quality*. Fixed with a lookbehind/lookahead guard on the quote regex and
   a bang-pattern fallback extractor.
2. **`generate_groq`/`_call_llm` only read `message["content"]`.** Groq's
   `openai/gpt-oss-120b` sometimes puts its *entire* output — including the
   final JSON tool call — into a separate `"reasoning"` field and leaves
   `"content"` empty for anything non-trivial. Confirmed directly: a
   throwaway "Say OK" prompt returns real `content`, but the strict
   tool-call JSON this loop asks for often doesn't. Fixed by falling back
   to `"reasoning"` when `"content"` is empty.
3. **The system prompt never told the model each tool's exact argument
   names.** The model reliably guessed plausible-but-wrong names for
   `compare_versions` (`version1`/`version2` instead of `query`) — Pydantic
   silently drops unrecognized keys rather than erroring, so the tool
   quietly ran with a generic default query, discarding the actual
   question context. Fixed by deriving each tool's real argument names
   from its Pydantic schema and printing them in the prompt
   (`compare_versions(query)`), plus an explicit rule against inventing
   names.
4. **300 completion tokens was too tight.** The model sometimes wrote the
   *entire prospective answer* into the terse `"thought"` field instead of
   the one-liner asked for, truncating mid-JSON before the closing brace —
   a working tool call turned into a `parse_error`. Fixed with an explicit
   "one sentence, under 25 words" rule plus delegating the *real* answer to
   the same generator the workflow uses (next point), so the loop's own
   JSON never needs to carry a full answer.
5. **A free-tier Groq key caps at 8,000 tokens/minute.** A 429 was being
   silently swallowed and treated as "no LLM available," making the
   workflow's real answers quietly fall back to the deterministic
   extractive generator with `est_cost_usd` reported as `$0.0000` for every
   question — invisible in the numbers as anything other than "the
   generator field happens to say extractive." Confirmed directly: the
   same question answered correctly via Groq when called standalone,
   immediately after a race run where it had "failed." Fixed with
   retry-with-backoff (`rag_core/generators.py::_post_groq_with_retry`,
   shared by both `generate_groq` and the agent's `_call_llm`) that
   respects `Retry-After`.

None of these are retrieval or corpus problems — they're integration bugs
in the LLM plumbing that a smaller, faster smoke test (one question, read
the raw JSON) caught in minutes each, and that a "just look at the final
pass-rate number" check would never have surfaced.

### Why pass rate isn't higher than 60%, honestly

- **The 8,000 TPM free-tier cap is a real, structural constraint on this
  race, not a code bug left unfixed.** The agent makes 2-5 LLM calls per
  question (one per reasoning step, `max_steps` capped at 4 here
  specifically to fit the budget better than the general-purpose default
  of 5); the workflow makes 1. Running 10 questions back-to-back
  regularly exhausts the per-minute budget, forcing the retry logic into
  15-30s backoffs and occasionally producing a malformed tool call under
  time pressure (a real, not simulated, source of the agent's remaining
  `parse_error`/early-finish runs). This is itself a legitimate finding for
  a "when not to use an agent loop" assignment: a loop's *N-calls-per-task*
  cost structure hits infrastructure limits a single-call workflow doesn't,
  independent of either system's actual reasoning quality.
- **The remaining failures (H02, H07, some runs of H05/H06) are a real
  ceiling of the underlying PDF text extraction**, not the tools or the
  generator: `H02`'s exact answer chunk retrieves at rank #1 with a strong
  score (0.78), but the extracted text itself is scrambled by a
  multi-column PDF layout (`Behaves as in 2.x, with one addition: v3 also
  honors a.openapi-generator-ignore-style negation / support did not exist
  in 2.x.` — the real content, reordered). A real LLM reconstructs the
  correct answer from this fine when given a clean shot at it (verified
  directly), but under rate-limit pressure and a short reasoning budget it
  doesn't always get one.
- **Two rounds of "obviously more correct" retrieval fixes were tried and
  reverted** after empirically making pass rate *worse*: (1) a
  text/filename-based fallback for `get_version_info` (whose `sdk_version`
  metadata is always empty for these PDFs — a real limitation, documented
  rather than silently patched) surfaced real version-specific chunks, but
  diluted the deterministic extractive picker's candidate pool; (2) routing
  2-version questions through `compare_versions` in the fixed planner did
  the same. Both are left as `get_version_info`'s documented no-op path
  rather than "fixed" into a regression — a concrete example of the
  module's lesson in the retrieval layer, not just the agent-vs-workflow
  one: more machinery isn't automatically better.

---

## Verdict

See `race_results.json["recommendation"]` for the exact, numbers-driven
paragraph regenerated on every run. Latest (verbatim, 147 words):

> Decision rule: does the correct path vary by input? Only 4/10 questions
> (H01, H04, H06, H08) have step 3 depend on what step 2 finds (a named
> parameter changed for a target api_version, so `check_deprecation` must
> resolve the replacement) — the agent actually took that branch on 0/4 of
> them this run, the workflow never branches (it always runs all 3 tools).
> Even so, that variation is one describable rule, not open-ended
> planning: pass rate is 60% (agent) vs 60% (workflow), the agent is 2.7x
> faster, and tokens/cost are ~20k tok/$0.0051 (agent) vs ~33k tok/$0.0041
> (workflow) — workflow is cheaper here, but that ordering isn't the point:
> the branch itself is one describable rule, so it belongs hard-coded as a
> conditional in the fixed workflow rather than run through a full
> autonomous loop either way. **Verdict: none of these 10 questions needs a
> genuine autonomous loop.**

The honest reading of the decision rule ("does the path vary by input?")
is that it's technically satisfied by the 4 dependency questions — but the
variation is a single, fully describable `if` (subject changed at target
version → look up replacement), so it belongs in the fixed workflow as one
conditional branch, not in a general-purpose planning loop. A real
autonomous agent would only earn its keep here if the *branching logic
itself* were unpredictable/open-ended (e.g. an ambiguous question where
which lookup to try next can't be pre-written) — none of these 10 fits
that description. Which side wins speed/cost is left to fluctuate with the
actual numbers each run (see the token-mix note below) rather than
asserted in one fixed direction, since with a real LLM in the loop that
ordering isn't stable run to run — the structural argument above is.

---

## Caveats (read before trusting any single run's numbers)

- **A free-tier Groq key caps at 8,000 tokens/minute** — see "Why pass
  rate isn't higher than 60%" above. Expect p50/p99 latency and even
  pass-rate to swing noticeably between runs depending on how much of that
  budget prior calls (in this session, or literally anywhere else using
  the same key) have already consumed. p50 is still the more trustworthy
  number than p99, which can spike to 60-90s on a run that hits the retry
  ceiling.
- **Which system is cheaper/faster can flip run to run.** The agent's
  several small calls and the workflow's one large call trade off
  differently depending on the real input/output token mix each gets
  charged for (`PRICE_PER_1K_OUTPUT` is 5x `PRICE_PER_1K_INPUT` in
  `rag_core/settings.py`) — don't read a single run's cost ordering as a
  fixed architectural property.
- **`total_api_calls` is not a fair cross-system comparison metric** — for
  the agent it counts tool calls (some local/free, some the LLM
  tool-selection calls), for the workflow it counts only the one final
  generation call. It's reported per-system for transparency, but the
  race's tie-breaks and cost comparisons use `est_tokens`/`est_cost_usd`
  instead, which *are* computed the same way for both.
- **Per-question "winner" only reflects answer-quality differences**
  (pass/fail, then relevance score) — when both systems land on identical
  pass/fail and score, `race.py` reports an honest `"tie"` rather than
  resolving it by whichever system happened to use fewer tokens that
  question (that comparison belongs in the separate aggregate speed/cost
  numbers, not manufactured into a per-question sweep).

---

## Run it yourself

```bash
# Full race (10 scenarios; builds/reuses an isolated index under
# week7_agent/.race_index/ from corpus/dev_docs/). Takes a few minutes
# with a real LLM key under free-tier rate limits (retries back off).
python -m week7_agent.race
#  -> week7_agent/race_results.json, week7_agent/race.csv

# Quick 3-scenario subset (NOTE: overwrites race_results.json/race.csv —
# re-run the full race afterward before submitting)
python -m week7_agent.race --quick

# Prove all 4 budgets terminate cleanly
python -m week7_agent.budget_termination_demo
#  -> week7_agent/budget_termination_log.txt

# API server
python -m uvicorn server.main:app --reload --port 8000
#   POST /api/agent            { "question": "..." }
#   GET  /api/agent/race
```

In the UI, the **Agent** tab has a playground (step-by-step reasoning, runs
over whatever documents are indexed in the live app) and a race-comparison
view (always runs against the real `corpus/dev_docs/` corpus).
