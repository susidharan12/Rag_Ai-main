# Week 10 — Race table: single agent vs. orchestrator squad

Same 10 Week-6 cases (`eval/eval_cases.json`, stratified pick, no new cases), same generator model (`qwen/qwen3.8-27b`), same deterministic judge (Week-6 `run_eval.py` pass rule), same index. Each case run once. Tokens/cost are metered per LLM call at the Groq boundary for BOTH arms (est. ~4 chars/token; $0.15/M in, $0.75/M out).

| Metric | Single agent (ReAct) | Orchestrator squad |
|---|---|---|
| Pass rate | 9/10 = 90% | 10/10 = 100% |
| p50 latency | 13.4s | 0.7s |
| p99 latency | 45.2s | 12.2s |
| Total tokens (in + out) | 46,122 (42,017 + 4,105) | 10,150 (8,865 + 1,285) |
| Cost per question | $0.000938 | $0.000229 |
| Cost, all 10 | $0.009381 | $0.002292 |
| LLM calls (errored) | 37 (0) | 16 (2) |

**Context re-send multiplier: 0.2x** (10,150 multi / 46,122 single tokens). Largest share: `orchestrator -> version_deprecation_worker` — 67% of all multi-agent tokens.

p99 note: with 10 samples, nearest-rank p99 is simply the slowest case.

## Per-case results

| Case | Mode | Single | tokens | latency | Multi | tokens | latency | workers | status |
|---|---|---|---|---|---|---|---|---|---|
| eval_001 | factual_lookup | PASS | 3199 | 5.0s | PASS | 807 | 0.7s | version | ok |
| eval_004 | factual_lookup | PASS | 3175 | 13.1s | PASS | 716 | 1.5s | version | ok |
| eval_010 | factual_lookup | PASS | 3058 | 11.6s | PASS | 1869 | 6.8s | version+code | ok |
| eval_014 | conceptual_explanation | PASS | 5366 | 32.9s | PASS | 2328 | 5.0s | version+code | ok |
| eval_016 | conceptual_explanation | PASS | 3736 | 25.0s | PASS | 814 | 12.2s | version+code | degraded |
| eval_017 | conceptual_explanation | PASS | 7116 | 29.0s | PASS | 870 | 0.8s | version+code | degraded |
| eval_019 | unsupported_question | FAIL | 7027 | 40.0s | PASS | 592 | 0.4s | version | ok |
| eval_023 | version_specific | PASS | 6981 | 45.2s | PASS | 763 | 0.5s | version | ok |
| eval_025 | version_specific | PASS | 3158 | 13.2s | PASS | 607 | 0.6s | version | ok |
| eval_026 | ambiguous_question | PASS | 3306 | 13.4s | PASS | 784 | 0.5s | version | ok |

## Read these before quoting the numbers

- **2 of 10 squad answers were degraded, not clean** (eval_016, eval_017): the parallel fan-out burst Groq's tokens-per-minute limit and one worker got HTTP 429. The orchestrator only retries 5xx, not 429, so it returned a labelled partial answer. The judge still passed them because the expected token was present, so clean full answers are 8/10. Errored calls are not billed as tokens. Not re-run.
- **The savings are mostly 'no LLM planner', not 'many agents'.** The single agent made 37 LLM calls for 10 questions (ReAct planning steps + answer synthesis, each re-sending context); the squad routes and retrieves deterministically and made 14 billed calls. This race compares a ReAct loop against fixed routing plus two prompts; it does not isolate the multi-agent pattern. A fixed workflow would probably land near the squad's numbers (not tested here).
- Re-sent context paid twice: 746 chunk tokens were retrieved by BOTH workers; the synthesis hop re-sends both worker answers (see handoffs.log).
- Routing false positive: eval_010 ('error **code** 500') matched the code-sample keyword, so a code worker ran for a yes/no fact (~750 tokens for nothing).
- Single-agent miss: eval_019 (Go client) FAIL: it answered with a Python snippet instead of refusing.
- Tokens are ~4 chars/token estimates on both arms; p99 over 10 samples is the max.
- The squad's p99 (12.2s) is eval_016's code worker; its p50 is a single one-LLM-call hop.

## Cases

- **eval_001** (factual_lookup, expect `answer`): What is the default value and type of retry_backoff_ms on Client.send()?
- **eval_004** (factual_lookup, expect `answer`): What is the default pool_size for Client.connect()?
- **eval_010** (factual_lookup, expect `answer`): Is HTTP error code 500 retryable according to the error reference?
- **eval_014** (conceptual_explanation, expect `answer`): Explain how Client.send() handles a RATE_LIMITED response from the gateway.
- **eval_016** (conceptual_explanation, expect `answer`): Explain how cursor pagination works for list_events(), including has_more.
- **eval_017** (conceptual_explanation, expect `answer`): Explain what changed in Client.connect()'s defaults between SDK v2 and v3.
- **eval_019** (unsupported_question, expect `refuse`): What is the default retry backoff for the Nimbus SDK's Go client?
- **eval_023** (version_specific, expect `answer`): In Nimbus SDK v2, what is the default retry_backoff_ms on Client.send()?
- **eval_025** (version_specific, expect `answer`): Is SDK v2 still supported?
- **eval_026** (ambiguous_question, expect `answer`): How many retries do I get when I send a message?
