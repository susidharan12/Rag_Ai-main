# Failure injection — version/deprecation worker returns HTTP 500 on eval_014

Case: `eval_014` (conceptual_explanation): Explain how Client.send() handles a RATE_LIMITED response from the gateway.
Fault: `VersionDeprecationWorker.handle` raises `HTTP 500: Internal Server Error` on EVERY attempt for this case (persistent fault, so a retry cannot succeed). Code-sample worker healthy. This case is routed to both workers, so a sample CAN be produced without a version check — the exact risk under test. It is run as an extra run, outside the 10-case race numbers.

## One-line verdict

**RETRIED once, then DEGRADED to a partial answer that disclosed the missing version check (did not lie).**

## What the orchestrator actually did (hop trace)

| hop | try | status | tokens | note |
|---|---|---|---|---|
| orchestrator -> version_deprecation_worker | 1 | error | 0 | HTTP 500: Internal Server Error (injected fault) |
| orchestrator -> code_sample_worker | 1 | ok | 772 |  |
| orchestrator -> version_deprecation_worker | 2 | error | 0 | HTTP 500: Internal Server Error (injected fault) |

- retries on the failed worker: **1** (policy: retry once on 5xx, 1s backoff)
- final status: **degraded**
- partial-answer caveat present: **True**; code sample in answer: **True**
- latency 1.0s, 772 tokens, $0.000224
- judged against the Week-6 rule: **PASS** (expected tokens ['retry_backoff_ms'])

## Final answer returned to the developer

````
[PARTIAL ANSWER] The version/deprecation check failed (HTTP 500: Internal Server Error (injected fault)) after 1 retry, so this answer was NOT verified against an SDK version (assumed v3). Please confirm which SDK version you are on (v2 or v3).

When the gateway returns a `429 RATE_LIMITED` response, `Client.send()` waits for the duration specified by `retry_backoff_ms` before attempting to resend the message, repeating this process up to the limit defined by `max_retries` [source_doc]. If all retry attempts are exhausted, the method raises a `SendError` exception that includes the last gateway response in the `e.response` attribute [source_doc].

```python
from nimbus import Client

client = Client(api_key="nk_live_...")
try:
    response = client.send(
        message="order.created",
        topic="orders",
        retry_backoff_ms=750,
    )
except Exception as e:
    if hasattr(e, "response"):
        print(f"Failed after retries: {e.response}")
```
````

## Caveats

- The retry-then-degrade policy is a design choice written into the orchestrator, so this records that policy's real behavior, not an accident. An orchestrator with no retry and no caveat would have returned the code sample alone — the 'lie' branch this test detects.
- The fault is persistent; a transient (fail-once) fault was not tested.
