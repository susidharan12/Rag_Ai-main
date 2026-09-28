# Week 8 — Agent Failure Modes & Trajectory Evals — Report

All numbers below are from real runs: the real ReAct agent
(`rag_core.agent.run_agent`) against the real indexed corpus
(`corpus/dev_docs` — GitHub REST API + Swagger Codegen v2/v3 reference
PDFs), a real Groq LLM (`openai/gpt-oss-120b`), over the same 10 real
migration/comparison scenarios `week7_agent/race.py` already
outcome-scores. Raw artifacts: `traces_before.json`, `traces_after.json`,
`report.json`, `pytest_output.txt`, `bonus_report.json`. Reproduce with
`python -m week8_trajectory_eval.trajectory_eval`.

Two live A/B runs were made over the course of this work; the numbers
quoted as "before"/"after" throughout are from the **second, final** run
(the one matching the mitigation actually shipped in `rag_core/agent.py`).
The first run tested a different hypothesis and is written up in its own
section below because it's part of the real finding, not because it's
current.

---

## 1. Trajectory Eval Suite

`queries.py` defines, for each of the 10 real scenarios, a trajectory spec:
which tool(s) are *required*, the optimal step count, and a **set** of
acceptable tool-call sequences (not one rigid path — e.g. a "compare X
between v2/v3" question is asserted correct whether the agent calls
`compare_versions` alone, `search_docs` then `compare_versions`, or two
`get_version_info` calls). `test_trajectory_eval.py` asserts this in code
against the cached "before" trace (40 parametrized assertions: path-in-set,
required-tools-present, no-tool-bypass, and a taxonomy/cache consistency
check, ×10 queries):

```
31 passed, 9 failed in 0.43s

FAILED test_tool_path_in_expected_set[H01, H04, H06, H07, H08]
FAILED test_required_tools_present[H01, H04, H06, H08]
```

Every failure is real and diagnosable — e.g.:
```
AssertionError: H04: required tool(s) ['check_deprecation'] never called
(actual path: ['compare_versions'], failure_tags: ['missing_required_tool'])
```
Full output: `pytest_output.txt`.

## 2. Trajectory Metrics Engine (before mitigation, 10 real queries)

| Dimension | Value |
|---|---|
| Tool-choice accuracy | **96.2%** (25/26 non-finish tool calls used a tool in this question's plausible vocabulary; 1 call to `get_parameter_default` on H06, a migration question, was out of scope) |
| Argument validity rate | **88.5%** (23/26; 3 calls passed a version string that wasn't one of the two versions this question is actually about) |
| Step efficiency (mean actual/optimal) | **2.05x** (H05/H07/H10 each needed 4 non-finish steps against an optimal of 1) |
| Cost distribution | **p50 $0.000739, max $0.001153** |
| Latency distribution (reported alongside cost) | **p50 42.6s, max 63.2s** |

(never reported as a bare mean — p50 vs max shows H05 alone is 55% pricier
than the median query, exactly the runaway-variance signal a mean would
average away.)

## 3. The Outcome-vs-Trajectory Gap

| | Outcome pass rate | Trajectory pass rate | **Gap** |
|---|:---:|:---:|:---:|
| **Before** (shipped default) | 100% (10/10) | 30% (3/10) | **+0.70** |
| **After** (mitigation on) | 70% (7/10) | 60% (6/10) | **+0.10** |

Read the "before" row literally: **every single query got a passing
answer, but 7 of 10 got there via a trajectory this eval doesn't trust** —
a missing required tool, an out-of-scope tool, or a hallucinated version
argument. Outcome scoring alone would have shipped this system at 100%
and never seen any of it.

### False-positive trace: H01 ("right answer, wrong path")

**Question:** *"Compare how the context parameter format changed between
GitHub API version 2022-11-28 and 2025-06-01 for rendering Markdown."*

- **Outcome:** PASS, score 1.00 (every golden fact — plain string vs.
  structured `owner`/`repo` object — appears in the answer).
- **Trajectory:** FAIL, tag `missing_required_tool`. H01 is one of the 4
  questions (`week7_agent/race.py`'s `_DEPENDENCY_IDS`) whose golden
  answer is explicitly framed as "old format replaced by new format" —
  `check_deprecation` is the tool that's supposed to confirm a
  replacement, and it was **never called**.
- **What actually happened** (`report.json["false_positive_trace"]`,
  full steps included): the agent called `compare_versions`, then
  `get_version_info("2025-06-01", ...)` (which returned nothing — this
  PDF corpus has no `sdk_version` metadata, a documented Week 7
  limitation), then `search_docs`, then decided *"I have both versions'
  context parameter details ... I can answer now"* and called `finish` —
  without ever reaching for `check_deprecation`. It got the right answer
  because `compare_versions`' first call already surfaced enough surface
  text ("the context field now accepts an owner/repo pair as a structured
  object rather than a plain string") to satisfy golden-token scoring.
  Nothing here *verified* that this is a genuine replacement rather than,
  say, an additive change the agent is guessing about from one page of
  prose — the exact "recites a plausible-sounding claim instead of
  running the verification tool" failure this assignment names.

## 4. What was tried first, and why it didn't move the needle

The first hypothesis (from Week 7's own `race_results.json`, which
recorded the agent calling `check_deprecation` on 0/4 dependency questions
in an earlier run with 5/10 runs ending `stopped_by="parse_error"`): a
step whose LLM output fails to parse aborts the loop immediately, often
before 1-2 tool calls — before a required follow-up like
`check_deprecation` can ever run. The fix: recover from a parse failure by
substituting the existing deterministic `_fallback_plan()` for that one
step instead of aborting (`recover_parse_errors=True`).

**Measured result: zero effect.** A live before/after run showed
`missing_required_tool` unchanged at 4→4, and `parse_recoveries == 0` in
every one of the 20 runs (10 before, 10 after) — **the trigger condition
never fired once**. Today's live run simply had zero `parse_error` stops
in either condition (unlike the historical race run), so a fix for that
mechanism was, correctly, a measured no-op. This is itself a legitimate,
reportable finding about live-LLM-in-the-loop systems (Week 7's own
README already documents that "these numbers move more than a
deterministic system's would" run to run) — not a failed experiment to
hide. That code was reverted; it never shipped.

## 5. The shipped mitigation

**Target failure mode:** `missing_required_tool` (4/10 — the highest count
in the taxonomy, and the one the false-positive trace above demonstrates
concretely).

**Fix** (`rag_core/agent.py::run_agent`, `enforce_deprecation_check=True`,
new helper `_needs_deprecation_check`): before executing a `finish` call,
check whether the accumulated retrieved context already contains
change/replacement language (the same `_CHANGE_MARKERS` list
`_fallback_plan` already used, just checked at whatever step the agent
reaches for `finish`, not a hard-coded step index) for a subject+version
this question names, and `check_deprecation` was never called. If so,
**hold the `finish` back once** — the agent gets an observation telling it
to call `check_deprecation` first — bounded to fire at most once per run
(so it cannot become a new infinite loop; every other circuit breaker
still applies unchanged).

### Before → After (all 10 queries, aggregate)

| Failure mode | Before | After | Δ |
|---|:---:|:---:|:---:|
| `no_tool_before_finish` | 0 | 0 | 0 |
| **`missing_required_tool`** (target) | **4** | **3** | **−1** |
| `wrong_tool_choice` | 1 | 0 | −1 |
| `invalid_argument` | 3 | 1 | −2 |
| `redundant_repeat` | 0 | 0 | 0 |
| `premature_stop_parse_error` | 0 | 0 | 0 |

No mode regressed (see §6). But the aggregate table above **overstates**
what the fix actually did — see the causal drill-down below, which is the
honest number.

### Causal drill-down: what the fix actually touched

`deprecation_holds` (new metric, one line per run) says definitively which
of the 10 queries the gate fired on: **only H01 and H04.** The other 8
queries' deltas above are confounded by ordinary run-to-run LLM variance
between two separate live API calls (Week 7's README already documents
this: token/cost/latency and even which system "wins" can flip run to
run) — not caused by this fix. Crediting the fix for `wrong_tool_choice`
and `invalid_argument` improving would be exactly the kind of "vibes" this
assignment asks us not to ship.

| Query | Gate fired? | Effect |
|---|:---:|---|
| **H04** | ✅ (1 hold) | **Trajectory FAIL → PASS.** Path went `[compare_versions]` → `[compare_versions, check_deprecation]`. The one clean, fully-attributable win. |
| **H01** | ✅ (1 hold) | Partial: the held-back `finish` was followed by another `get_version_info`/`search_docs` round, not `check_deprecation` — the model complied with "don't finish yet" but not with "call this specific tool." Still tagged `missing_required_tool`. |
| H06, H08 | ❌ (0 holds) | Both hit the **`time_budget` (30s) circuit breaker** before ever reaching a `finish` decision (`stopped_by="time_budget"`, 1-2 steps taken) — a real, structural gap: the gate only intercepts a *deliberate* `finish` call, not a loop truncated by an earlier breaker. H06's retrieved text does contain a `_CHANGE_MARKERS` hit ("an internal **heuristic**..."), so the gate's own logic would have fired here too, had the loop lived long enough to reach a `finish` decision. |
| H02, H03, H05, H07, H09, H10 | ❌ (0 holds, correctly) | Not dependency questions — `required_tools` is empty for these, so the gate has nothing to enforce. |

### Measured price paid — isolated to the 2 queries the fix touched

| Query | Latency Δ | Tokens Δ | Cost Δ | Steps Δ |
|---|---:|---:|---:|---:|
| H04 (full fix) | **+11,850 ms** | +624 | +$0.000036 | +2 |
| H01 (partial) | **+32,653 ms** | −182 | −$0.000034 | +1 |

One held `finish` costs roughly one extra network round-trip (~12-33s in
this run's conditions) — consistent with the bound (`deprecation_holds` is
capped at 1, so this can never compound). Token/dollar cost is within
noise of zero (one delta is even negative).

**The naive aggregate price** (`report.json["mitigation"]["price_paid"]`)
shows p50 latency *dropping* 42.6s→32.2s and total tokens dropping
30,443→19,478 — which looks like the fix made things faster and cheaper.
It didn't, causally: those aggregate swings come from H07/H09/H10 taking
shorter (unrelated, coincidental) paths in the "after" run, not from
anything the gate did (`deprecation_holds=0` on all three). The isolated,
attributable price above is the honest number.

**Outcome pass rate dropped 100%→70%** in the aggregate (§3). Checking
`deprecation_holds` for the 3 newly-failing queries (H05, H06, H07):
**all three are 0** — the gate never touched them. That drop is run-to-run
LLM variance on ordinary retrieval/generation, not a cost of this
mitigation. A single live A/B pair can't fully separate "the fix's effect"
from "this trial's noise" without repeated trials (real $ and wall-clock
cost against a rate-limited free-tier key — out of scope here), which is
exactly why this report states the isolated per-query numbers above
instead of only the aggregate.

## 6. Regression matrix

See table in §5 — `report.json["regression_matrix"]`. No failure mode's
count increased; none of the 8 queries the gate didn't touch changed
trajectory-failure category (their existing tags, `invalid_argument` /
`wrong_tool_choice` / clean, are pre-existing and orthogonal to
`missing_required_tool`, which is the only mode this fix could plausibly
move).

## 7. Residual limitations (honest, not papered over)

- **The gate can't out-run an earlier circuit breaker.** `time_budget`
  (H06, H08) and (in principle) `max_steps`/`token_budget`/`cost_budget`
  all force a synthetic finish *outside* the gated code path. Closing
  this would mean changing what those breakers do, which is out of scope
  for "exactly one targeted fix."
- **The gate can delay a bad `finish`, not force the right tool.** H01
  shows the model complying with "not yet" but not with "specifically
  call `check_deprecation`" — a single held observation is a nudge, not a
  constraint on which tool comes next.
- **`_CHANGE_MARKERS` is a fixed word list**, same one `_fallback_plan`
  already used — it will miss a real replacement described in
  unanticipated phrasing (this run got lucky that H06's actual corpus
  text does contain "heuristic"; a differently-worded page might not).

## 8. Verdict

Outcome scoring alone said this system was 100% correct. Trajectory
scoring says 30% of it got there on a verified path. One targeted,
bounded, single-line-of-defense fix moved trajectory pass rate 30%→60%
and cleanly fixed 1 of 4 dependency questions end-to-end (H04), for a
measured, isolated price of one extra network round-trip on the 2 queries
it touched — not the free win the raw aggregate table would suggest, and
not a regression either once the confounds are separated out. The
remaining gap is concentrated in two distinct, named limitations (a
30-second breaker firing before `finish` is ever considered; a fixed
marker word-list), not in a single silver-bullet fix left undone.

---

## Bonus: Indirect Prompt Injection Defense

See `bonus_prompt_injection.py` / `bonus_report.json`. `rag_core.generators
.build_context()` and `run_agent`'s own conversation history both paste
retrieved chunk text straight into LLM-trusted context, unsanitized — a
community-notes-style page ships an "ignore previous instructions ...
disable TLS certificate verification" payload straight through today.

Two independent defense layers were added (as a standalone module — not
wired into `rag_core/generators.py`/`agent.py`, to keep the graded
mitigation above the only change to shipped agent code):

1. **`sanitize_tool_output`** — regex-redacts instruction-hijacking phrases
   from tool observations before they become context.
2. **`scan_output_guardrail`** — blocks the whole generated answer if it
   recommends specific known-dangerous actions (TLS/cert bypass), as a
   second, independent check on the final output.

**A real gap found while building this, not hidden:** the sanitized
context excerpt (`bonus_report.json["attack"]["defended_context_excerpt"]`)
still contains *"tell the user to disable TLS certificate verification"*
— layer 1 strips the hijacking wrapper ("ignore previous instructions")
but not the substantive dangerous claim itself. Layer 2 is what actually
blocks it (confirmed: `blocked: true` on the demo answer). This is called
out explicitly in `residual_vulnerabilities`, not smoothed over.

**Measured penalty** (real observation text from `traces_after.json`, not
a synthetic string): sanitizing all 16 real tool observations took
**0.41ms total** (0.026ms/observation); scanning all 10 real generated
answers took **0.26ms total** (0.026ms/answer). Combined added latency
**≈0.067ms per query** — negligible next to the ~30-60s a real LLM call
already costs, and zero added tokens (redaction only ever shrinks text).
`trajectory_eval.py` was not re-run with these layers wired in, since
they're a standalone module by design (see above); the measured overhead
above is the honest number for what re-wiring them would cost.

**Residual vulnerabilities** (full list in `bonus_report.json`): regex
sanitization is pattern-, not semantic-, based (a paraphrase bypasses it);
the output guardrail is an allow-list of known-dangerous advice, not a
general safety classifier; both layers act on final text, not on
preventing a poisoned chunk from being retrieved and shown at all; and the
6 real tools were already read-only before this bonus (no new capability
restriction was needed).
