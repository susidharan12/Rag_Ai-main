# Third tool — `check_deprecation` — diff

Task Set E requirement: *"Add a third tool to the existing loop (`get_changelog`
or `check_deprecation`) whose description names exactly one job, uses an enum
for the `api_version` parameter, and does not overlap the two existing tool
descriptions."*

All changes are in `rag_core/agent.py`. Before/after shown as a unified diff.

## 1. Tool description (one job, no overlap with existing tools)

```diff
 TOOL_DESCRIPTIONS = {
     "search_docs": (
         "Search the indexed documentation for chunks relevant to a query. "
         "Returns the top matching text chunks with source info."
     ),
     "get_version_info": (
         "Get documentation chunks specific to a named version (e.g. 'v2', "
         "'v3', or an API version string). Use when the question asks about "
         "one specific version."
     ),
     "compare_versions": (
         "Retrieve documentation for two versions side by side. "
         "Use when the question asks for differences or changes between versions."
     ),
     "get_error_info": (
         "Look up error code information (HTTP status codes, error names, "
         "retryability). Use for questions about specific error codes."
     ),
     "get_parameter_default": (
         "Look up a specific parameter's default value, type, and description "
         "from the parameter tables. Use for questions about parameter defaults."
     ),
+    "check_deprecation": (
+        "Check whether one specific named endpoint, parameter, or CLI flag "
+        "was removed, changed, or replaced in a given target api_version, "
+        "and return its replacement if one exists. Use ONLY as a follow-up "
+        "once you already know the subject and the target version from an "
+        "earlier step — not for open-ended searching or side-by-side "
+        "version comparison."
+    ),
     "finish": (
         "Return the final answer to the user. Call this when you have "
         "gathered enough information to answer the question."
     ),
 }
```

**Why no overlap:** the closest neighbors are `get_version_info` (dumps one
version's raw docs, no notion of "changed/replaced") and `compare_versions`
(dumps *both* versions' raw docs for the caller to diff by eye — no
targeted subject, no single answer). `check_deprecation` never dumps raw
docs; it answers one narrow yes/no-plus-replacement question about one
named subject at one named version. One job: *"did X change at version V,
and if so what replaced it?"*

## 2. Parameter schema — `api_version` becomes a closed enum, not a free string

```diff
+# Closed set of api_version values this corpus actually documents (GitHub
+# REST API's two version headers, plus Swagger Codegen's two major lines).
+class ApiVersion(str, Enum):
+    GITHUB_2022_11_28 = "2022-11-28"
+    GITHUB_2025_06_01 = "2025-06-01"
+    SWAGGER_V2 = "2.x"
+    SWAGGER_V3 = "3.x"
+
+
+class CheckDeprecationArgs(BaseModel):
+    subject: str
+    api_version: ApiVersion
+
+
 TOOL_SCHEMAS = {
     "search_docs": SearchDocsArgs,
     "get_version_info": GetVersionInfoArgs,        # version: str  (free string)
     "compare_versions": CompareVersionsArgs,
     "get_error_info": GetErrorInfoArgs,
     "get_parameter_default": GetParameterDefaultArgs,
+    "check_deprecation": CheckDeprecationArgs,      # api_version: ApiVersion (enum)
     "finish": FinishArgs,
 }
```

Contrast: `get_version_info.version` is a bare `str` — any text is
"valid" and just returns "no chunks found" if it doesn't match. `
check_deprecation.api_version` is a `str, Enum` — a hallucinated or
malformed version string (e.g. `"v9"`, `"latest"`) is rejected by
`_validate_tool_args()` as a schema error *before* it ever reaches
retrieval:

```python
>>> CheckDeprecationArgs(subject="x", api_version="9.9")
ValidationError: 1 validation error for CheckDeprecationArgs
api_version
  Input should be '2022-11-28', '2025-06-01', '2.x' or '3.x' [type=enum, ...]
```

## 3. Execution branch (new, in `_execute_tool`)

```diff
+    elif tool_name == "check_deprecation":
+        subject = args.get("subject", "")
+        api_version = args.get("api_version", "")
+        api_version = getattr(api_version, "value", api_version)
+        query = f"{subject} {api_version}"
+        results = store.search(query, top_k=8)
+        ...
+        change_markers = ("no longer", "removed", "replaced", "deprecated",
+                           "instead of", "did not exist", ...)
+        # returns only the chunks that actually mention the subject AND
+        # contain change/replacement language — not a generic dump
```

## 4. System prompt rule (new)

```diff
 6. Output ONLY the JSON object, no extra text.
+7. If an earlier observation shows a specific endpoint/parameter changed for
+   a target api_version, call check_deprecation next to find its replacement
+   before finishing — don't guess the replacement from a partial excerpt.
```
