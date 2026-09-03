---
sdk_version: v2
title: Nimbus SDK v2 - Client.send()
---

# Client.send()

**v2 is in maintenance mode.** Only security fixes are shipped; new integrations must use SDK v3. `Client.send()` publishes a single event message to the Nimbus gateway and blocks until acknowledgement. The v2 signature is compatible with v3 for the `message` and `topic` parameters, but the tuning defaults differ.

## Parameters

| parameter | type | default | required | description |
|---|---|---|---|---|
| message | str | - | yes | Event payload; must be valid JSON-serializable data. |
| topic | str | - | yes | Target topic, e.g. `order.created`. |
| retry_backoff_ms | int | 250 | no | Base backoff between retries after a failed send. |
| timeout_ms | int | 30000 | no | Total wall-clock budget for the send including retries. |
| max_retries | int | 3 | no | Maximum retry attempts before raising `SendError`. |

## Example

```python
from nimbus import Client

client = Client(api_key="nk_live_...")
response = client.send(message="order.created", topic="orders")
```

## Notes

In v2 the send path retries at most 3 times with a 250 ms base backoff. v3 raises the defaults to 5 retries with 500 ms base backoff and halves the total timeout from 30000 ms to 15000 ms. Migration guide: set the v2 values explicitly before upgrading if your service depends on the old timing behavior.
