---
sdk_version: v2
title: Nimbus SDK v2 - Client.connect()
---

# Client.connect()

**v2 is in maintenance mode.** Only security fixes are shipped; new integrations must use SDK v3. `Client.connect()` establishes the connection pool used by subsequent calls. The v2 pool defaults are smaller because the v2 gateway accepted fewer concurrent streams per key.

## Parameters

| parameter | type | default | required | description |
|---|---|---|---|---|
| api_key | str | - | yes | Nimbus API key, prefixed `nk_live_` or `nk_test_`. |
| region | str | "eu-west" | no | Gateway region to connect against. |
| pool_size | int | 5 | no | Maximum concurrent connections held open to the gateway. |

## Example

```python
from nimbus import Client

client = Client.connect(api_key="nk_live_...", pool_size=5)
```

## Notes

`pool_size` sets the maximum number of concurrent TCP connections held open to the gateway; the v2 default is `5`. v2 is in maintenance mode, and v3 doubles the default `pool_size` to `10`. The `keepalive_ms` parameter does not exist in v2; keepalive behavior is fixed at 30 second intervals.
