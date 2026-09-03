---
sdk_version: v3
title: Nimbus SDK v3 - Client.send()
---

# Client.send()

`Client.send()` publishes a single event message to the Nimbus gateway and waits for an broker acknowledgement. It is the primary write path of the SDK and is safe to call concurrently from multiple threads on a shared `Client` instance. The call blocks until either the gateway acknowledges the event or the configured timeout elapses, whichever comes first.

## Parameters

| parameter | type | default | required | description |
|---|---|---|---|---|
| message | str | - | yes | Event payload; must be valid JSON-serializable data. |
| topic | str | - | yes | Target topic, e.g. `order.created`. |
| retry_backoff_ms | int | 500 | no | Base backoff between retries after a failed send. |
| timeout_ms | int | 15000 | no | Total wall-clock budget for the send including retries. |
| max_retries | int | 5 | no | Maximum retry attempts before raising `SendError`. |

## Example

```python
from nimbus import Client

client = Client(api_key="nk_live_...")
response = client.send(
    message="order.created",
    topic="orders",
    retry_backoff_ms=750,
)
```

## Notes

If the broker returns a `429 RATE_LIMITED` response, `Client.send()` will honor `retry_backoff_ms` before retrying, up to `max_retries` attempts. When all retries are exhausted the method raises `SendError` with the last gateway response attached under `e.response`. In SDK v2 the default `timeout_ms` was `30000`; v3 halved it to `15000` to fail fast during incidents.
