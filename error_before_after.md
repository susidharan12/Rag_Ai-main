# Error Handling: Before/After Transcript

## Tool: `get_version_info` (docs-search server)

### Scenario
Model asks for documentation for version `v4.x` which does not exist in the corpus.

---

## BEFORE (Old Docstring + Opaque Error)

**Tool Docstring (old):**
```
"Get documentation chunks specific to a named version (e.g. 'v2', 'v3', or an API version string). Use when the question asks about one specific version."
```

**Model Call:**
```json
{"tool": "get_version_info", "args": {"version": "v4.x", "query": "authentication"}}
```

**Tool Response (old):**
```
"No chunks found specifically for version v4.x."
```

**Model Reasoning (next step):**
> The tool returned "No chunks found specifically for version v4.x." I don't know if v4.x doesn't exist at all, or if it exists but has no matching chunks. I'll try searching without a version filter.

**Model Follow-up Call:**
```json
{"tool": "search_docs", "args": {"query": "authentication v4.x"}}
```

**Result:** Wasted turn. Model had to guess what to do next. No actionable guidance from tool.

---

## AFTER (Rewritten Docstring as Prompt + Recoverable Error)

**Tool Docstring (new - rewritten as prompt):**
```
"Get documentation chunks specific to a named version (e.g. 'v2', 'v3', or an API version string). Use when the question asks about one specific version. 

IMPORTANT: If the requested version does not exist in this corpus, the tool returns a structured error object with:
- 'error': human-readable message
- 'recovery_hint': exact next tool call to make (e.g., 'Try get_version_info(version=\"3.x\") instead')
- 'available_versions': list of all versions this corpus knows about

READ the recovery_hint and follow it — do not guess."
```

**Model Call (same failing call):**
```json
{"tool": "get_version_info", "args": {"version": "v4.x", "query": "authentication"}}
```

**Tool Response (new - recoverable error):**
```json
{
  "error": "No documentation found for version 'v4.x'",
  "recovery_hint": "Available versions in this corpus: v2, v3, 2022-11-28, 2025-06-01, 2.x, 3.x. Latest is '3.x'. Try get_version_info(version='3.x') instead.",
  "available_versions": ["v2", "v3", "2022-11-28", "2025-06-01", "2.x", "3.x"]
}
```

**Model Reasoning (next step):**
> The tool returned a structured error with a clear recovery_hint: v4.x doesn't exist, available versions are listed, and it explicitly tells me to try get_version_info(version='3.x'). I'll follow that hint.

**Model Follow-up Call (guided by recovery_hint):**
```json
{"tool": "get_version_info", "args": {"version": "3.x", "query": "authentication"}}
```

**Tool Response (success):**
```json
{
  "results": [
    {"chunk_id": "...", "score": 0.89, "source_doc": "github_combined_reference.pdf", "sdk_version": "3.x", "text": "Authentication in v3 uses Bearer tokens..."},
    ...
  ]
}
```

**Model Final Answer:**
> Version 3.x (latest) uses Bearer token authentication... [complete answer using retrieved docs]

---

## Key Difference

| Aspect | Before | After |
|--------|--------|-------|
| Error format | Plain string "No chunks found..." | Structured object with `error`, `recovery_hint`, `available_versions` |
| Model's next action | Guess (try search_docs) | Follow explicit `recovery_hint` |
| Turns wasted | 1+ (guessing) | 0 (direct guidance) |
| User-visible outcome | "I couldn't find v4.x docs" → vague | "v4.x doesn't exist; latest is 3.x which has..." → precise |

---

## Another Example: Version Exists But No Tagged Chunks

**Model Call:**
```json
{"tool": "get_version_info", "args": {"version": "v3", "query": "rate limiting"}}
```

**Tool Response (recoverable):**
```json
{
  "error": "No chunks found specifically for version v3.",
  "recovery_hint": "Version 'v3' exists in corpus but no version-tagged chunks matched. Try search_docs(query='rate limiting') for unversioned results, or get_version_info(version='3.x') for latest.",
  "available_versions": ["v2", "v3", "2022-11-28", "2025-06-01", "2.x", "3.x"],
  "fallback_results": [...]  // 3 unversioned results for context
}
```

**Model Follow-up (guided):**
```json
{"tool": "search_docs", "args": {"query": "rate limiting"}}
```

**Result:** Model immediately tries the suggested alternative instead of hallucinating or giving up.