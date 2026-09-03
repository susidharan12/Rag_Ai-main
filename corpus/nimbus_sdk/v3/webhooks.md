---
sdk_version: v3
title: Nimbus SDK v3 - Webhooks
---

# Webhooks

Nimbus delivers event callbacks to HTTPS endpoints you register in the dashboard. Every delivery is signed with the endpoint's signing secret so your server can verify the payload was produced by Nimbus and was not replayed. Deliveries are retried by the Nimbus delivery worker for up to 24 hours with exponential backoff, independent of anything configured in the SDK.

## WebhookVerifier.verify()

| parameter | type | default | required | description |
|---|---|---|---|---|
| payload | bytes | - | yes | Raw request body exactly as received. |
| signature_header | str | - | yes | Value of the `X-Nimbus-Signature` header. |
| secret | str | - | yes | The endpoint signing secret (`whsec_...`). |
| tolerance_seconds | int | 300 | no | Maximum allowed clock skew for signed timestamps. |

## Example

```python
from nimbus.webhooks import WebhookVerifier

verifier = WebhookVerifier(secret="whsec_...")
event = verifier.verify(payload=request.body,
                        signature_header=request.headers["X-Nimbus-Signature"])
```

## Notes

`verify()` raises `SignatureVerificationError` when the signature does not match or when the signed timestamp is older than `tolerance_seconds`. The tolerance protects you against replay attacks; it does not need to match any server-side setting.
