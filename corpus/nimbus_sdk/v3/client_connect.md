---
sdk_version: v3
title: Nimbus SDK v3 - Client.connect()
---

# Client.connect()

`Client.connect()` establishes the persistent connection pool used by all subsequent calls on the returned `Client`. Calling it is optional: the first `send()` will connect lazily with the same defaults. Explicit connects are recommended for latency-sensitive services so the pool warms up before the first request.

## Parameters

| parameter | type | default | required | description |
|---|---|---|---|---|
| api_key | str | - | yes | Nimbus API key, prefixed `nk_live_` or `nk_test_`. |
| region | str | "eu-west" | no | Gateway region to connect against. |
| pool_size | int | 10 | no | Maximum concurrent connections held open to the gateway. |
| keepalive_ms | int | 60000 | no | Interval between keepalive pings on idle connections. |

## Example

```python
from nimbus import Client

client = Client.connect(
    api_key="nk_live_...",
    region="us-east",
    pool_size=20,
)
```

## Notes

`pool_size` sets the maximum number of concurrent TCP connections held open to the gateway. In SDK v2 the default `pool_size` was `5`; v3 doubled it to `10`. Raising `pool_size` above 32 requires a written quota increase from Nimbus support; the gateway rejects handshakes beyond the quota with error code `POOL_QUOTA_EXCEEDED`.
