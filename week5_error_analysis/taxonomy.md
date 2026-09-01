# Failure Taxonomy — Week 5 Error Analysis

Clustered bottom-up from the open-coded sample (see `notes.md`). Severity legend: 🔴 ships broken code to a user's repo · 🟡 merely annoys the reader.

## Retrieval vs Stored-Answer Split

### Retrieval Failures

| Failure | Evidence | Reason |
|---|---|---|
| Wrong SDK version wins for an unversioned question | `tr_20260824_131138_576c5d`, `tr_20260824_131138_d00a20` | v2 and v3 chunks searched together; similar wording lets a v2 chunk outrank the v3 default → stale value. |
| Version-history chunks outrank the current-value chunk | `tr_20260824_131138_416582`, `tr_20260824_131138_547c7a` | Query matches change-log language ("was", "raised", "halved") more strongly than the current parameter row. |
| Out-of-corpus questions retrieve unrelated chunks | `tr_20260824_131138_244ba5`, `tr_20260824_131138_d7cd4c` | Dense similarity always returns the nearest text; no relevance gate converts low-confidence match into a refusal. |
| Unrelated documents contaminate top results | `tr_20260824_131138_547c7a`, `tr_20260824_131138_395aa7` | Index mixes SDK docs + sports PDF with no domain/metadata filter; generic words place sports chunks beside SDK chunks. |
| Relevant row ranked below a large table / truncated | `tr_20260824_131138_158606`, `tr_20260824_131138_aa8066` | Chunk boundaries + top-k don't guarantee the exact parameter/error row is in the selected context. |
| Vague / misspelled query retrieves only broad topical evidence | `tr_20260826_141604_f8f24b` | Misspelled underspecified query finds the Core Bluetooth topic but not the intended error codes. |

### Stored-Answer Failures

| Failure | Evidence | Reason |
|---|---|---|
| Correct evidence retrieved but requested number absent | `tr_20260824_131138_c41aed`, `tr_20260824_131138_3b14d5`, `tr_20260824_131138_395aa7`, `tr_20260824_131138_1116f0` | Extractive generator selects nearby sentences without checking that every requested field appears. |
| Answer uses a stale v2 value | `tr_20260824_131138_576c5d` | Final answer follows highest-ranked v2 evidence without resolving version ambiguity. |
| Answer leads with v2→v3 change instead of current value | `tr_20260824_131138_416582`, `tr_20260824_131138_547c7a` | Extractive selection favors a highly similar historical sentence; no rule requires current value first. |
| Confident response to unanswerable question | `tr_20260824_131138_244ba5`, `tr_20260824_131138_d7cd4c` | Generator answers whenever chunks exist; no minimum-evidence or answerability check. |
| Duplicate sentence | `tr_20260824_131138_c31a87`, `tr_20260826_131637_f71776` | Multiple near-duplicate chunks selected; generator doesn't dedupe extracted sentences. |
| Correct fact buried in table/list dump | `tr_20260824_131138_5fddc2`, `tr_20260824_131138_8d8b3b`, `tr_20260824_131138_158606` | Answer preserves a large source fragment rather than extracting the exact field. |
| Answer drifts into generic/unrelated context | `tr_20260824_131138_59beb9`, `tr_20260824_131138_791fc2`, `tr_20260824_131138_106141` | No final relevance check; a second chunk can add a cover page, overview, or contradiction. |
| Current Core Bluetooth answer incomplete | `tr_20260826_141604_f8f24b` | Names `CBError`/`CBATTError` but doesn't list requested error codes; generation stopped at shallow summary. |

## Consolidated Mode Summary

| Mode | Count | Frequency | Main Reason ||---|---:|---:|---|
| Stale v2 default | 2 | 10% | No SDK-version filtering / ambiguity resolution 
| Change-log sentence first | 2 | 10% | Historical text scores highly, copied first |
| Unrelated answer instead of refusal | 2 | 10% | No evidence threshold / answerability check |
| Requested number missing | 4 | 20% | No required-field / question-coverage check |
| Duplicate sentences | 3 | 15% | No deduplication after extraction |
| Fact buried or truncated | 3 | 15% | Table-like chunks copied as blobs |
| Second-half drift | 3 | 15% | No final relevance / contradiction check |

Largest single mode = omission of the requested value (M4). Highest-risk retrieval = version mixing + unrelated-document contamination. Highest-risk stored-answer = confidently answering when evidence doesn't support the question.

---

## Prompt Version Configuration (change log)

The two prior prompt-version constants (`PROMPT_VERSION_LLM = "grounded-strict-v2"`,
`PROMPT_VERSION_EXTRACTIVE = "extractive-grounded-v1"`) were collapsed into a single
env-configurable `PROMPT_VERSION` defaulting to `"v1"` (`rag_core/settings.py`).

- Both generators (`generate_groq`, `generate_extractive`) now report `settings.PROMPT_VERSION` in `generation.prompt_version`.
- Switch versions later by setting `PROMPT_VERSION` in `.env`/environment — no code change needed.
- Replay/trace consistency: every turn tags the active version, so version-based analysis stays uniform across both generators.

See `notes.md` §7 for the full description.
