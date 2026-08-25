---
sdk_version: v3
title: Nimbus SDK v3 - Auth
---

# Authentication

The SDK authenticates with API keys. Keys are scoped: a key issued for read-only dashboards cannot publish events. Create and rotate keys in the Nimbus dashboard under Settings, API keys. The SDK never transmits the key to any endpoint other than the gateway of your selected region.

## TokenProvider.refresh()

| parameter | type | default | required | description |
|---|---|---|---|---|
| api_key | str | - | yes | The key to exchange for a short-lived access token. |
| scope | str | "read:events" | no | Requested scope; must be a subset of the key's scopes. |
| ttl_seconds | int | 3600 | no | Lifetime of the minted access token. |

## Example

```python
from nimbus.auth import TokenProvider

provider = TokenProvider(api_key="nk_live_...")
token = provider.refresh(scope="write:events", ttl_seconds=1800)
```

## Notes

`refresh()` mints an access token valid for `ttl_seconds`. When `scope` is omitted the token defaults to `read:events`; requesting a scope outside the key's grants raises `InsufficientScopeError`. Access tokens are cached per (scope, ttl) pair until 60 seconds before expiry.
