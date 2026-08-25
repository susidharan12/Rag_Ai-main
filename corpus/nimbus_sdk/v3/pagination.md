---
sdk_version: v3
title: Nimbus SDK v3 - Pagination
---

# Pagination

List endpoints in the Nimbus API are cursor-paginated. Every list response contains `data`, a `next_cursor` for the following page, and has_more. Pass the cursor back via the `cursor` parameter until `has_more` is false. Cursors expire after 24 hours; treat them as opaque strings and never construct them yourself.

## Parameters (list_events)

| parameter | type | default | required | description |
|---|---|---|---|---|
| cursor | str | None | no | Opaque cursor from a previous response. |
| limit | int | 50 | no | Page size, accepted range 1 to 200. |
| created_after | str | None | no | ISO-8601 timestamp filter. |

## Example

```python
page = client.list_events(limit=100, cursor=next_cursor)
for event in page.data:
    process(event)
```

## Notes

`limit` accepts any integer from `1` to `200`. Requesting a `limit` above `200` raises a client-side `ValueError` before any request is sent; the server additionally rejects such requests with `400 INVALID_ARGUMENT`. In SDK v2 the maximum allowed `limit` was `100`; the cap was raised to `200` in v3.
