---
sdk_version: v3
title: Nimbus SDK v3 - Errors
---

# Error handling

All SDK exceptions derive from `NimbusError`. Network-level failures raise `TransportError`; gateway rejections raise `ApiError` with a machine-readable `code` matching the table below. Retryable errors are safe to retry with backoff; non-retryable ones indicate a problem with the request itself and will fail again unchanged.

## Codes

| code | http | retryable | meaning |
|---|---|---|---|
| INVALID_ARGUMENT | 400 | no | Malformed request; fix the parameters. |
| UNAUTHENTICATED | 401 | no | Missing or revoked API key. |
| INSUFFICIENT_SCOPE | 403 | no | Key lacks the requested scope. |
| RATE_LIMITED | 429 | yes | Too many requests; back off and retry. |
| POOL_QUOTA_EXCEEDED | 429 | yes | Concurrent connection quota exceeded. |
| INTERNAL | 500 | yes | Gateway-side fault. |

## Example

```python
from nimbus.errors import ApiError, TransportError

try:
    client.send(message="ping", topic="health")
except ApiError as e:
    if e.retryable:
        schedule_retry(e.code)
except TransportError:
    schedule_retry("TRANSPORT")
```

## Notes

The `retryable` column is the source of truth for automatic retry logic in the SDK itself; `send()` already retries retryable codes up to `max_retries` times. Application code should still catch `NimbusError` to surface permanent failures.
