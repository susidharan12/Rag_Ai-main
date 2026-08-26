Here is the corrected and polished version:

# Retrieval and Stored Answer Failure Analysis

## Scope

This document separates failures caused by **retrieval** from failures caused by the **stored/generated answer**. The evidence comes from the seeded Week 5 sample documented in `week5_report.md` and the current trace in `traces/traces.jsonl`.

A **retrieval failure** occurs when the required evidence is not retrieved, is ranked too low, or unrelated evidence contaminates the context. A **stored-answer failure** occurs when the required evidence is available, but the final answer omits it, contradicts it, duplicates it, or presents it unclearly.

## Retrieval Failures

### Embedding-Specific Findings

There is **no evidence of an embedding runtime failure** in the stored traces or retrieval code. The configured model is consistently `sentence-transformers/all-MiniLM-L6-v2`; vectors are converted to `float32`, L2-normalized, and searched with FAISS inner-product similarity. No trace records an embedding exception, invalid vector, dimension mismatch, or NaN score.

There **are embedding-quality failure symptoms** in retrieval:

| Finding | Evidence | Reason |
|---|---|---|
| Semantically similar but wrong-version chunks enter the top results | `tr_20260824_131138_576c5d`, `tr_20260824_131138_d00a20` | Dense embeddings capture shared meaning and terminology, but do not know that an unversioned question should prefer v3 over v2. Metadata filtering is required for that distinction. |
| Semantically related but unrelated-domain chunks enter the top results | `tr_20260824_131138_547c7a`, `tr_20260824_131138_395aa7` | Generic terms such as `default`, `client`, or `connect` can make SDK and sports-document vectors appear similar enough to survive top-k retrieval. |
| Low-confidence out-of-corpus queries still return chunks | `tr_20260824_131138_244ba5`, `tr_20260824_131138_d7cd4c` | FAISS returns nearest neighbors even when none are genuinely relevant. A score threshold helps, but answerability and domain checks are also needed. |
| Vague or misspelled queries retrieve only broad topical evidence | `tr_20260826_141604_f8f24b` | The query is misspelled and underspecified. Embeddings find the Core Bluetooth error topic, but cannot infer which error codes or details the user intended. |

These are **embedding-assisted retrieval failures**, not proof that the embedding model is broken. The main root causes are missing metadata filters, mixed domains in one index, and no semantic answerability check after retrieval.

| Failure                                                        | Evidence                                                 | Reason                                                                                                                                                         |
| -------------------------------------------------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Wrong SDK version wins for an unversioned question             | `tr_20260824_131138_576c5d`, `tr_20260824_131138_d00a20` | v2 and v3 chunks are searched together. Similar wording allows a v2 chunk to outrank the v3 default, causing the answer to use stale values.                   |
| Version-history chunks outrank the current-value chunk         | `tr_20260824_131138_416582`, `tr_20260824_131138_547c7a` | The query matches change-log language such as `was`, `raised`, or `halved` more strongly than the current parameter row.                                       |
| Out-of-corpus questions retrieve unrelated chunks              | `tr_20260824_131138_244ba5`, `tr_20260824_131138_d7cd4c` | Dense similarity always returns the nearest available text. There is no strong enough relevance gate to convert a low-confidence match into a refusal.         |
| Unrelated documents contaminate the top results                | `tr_20260824_131138_547c7a`, `tr_20260824_131138_395aa7` | The index contains SDK documentation and a sports PDF without a domain or metadata filter. Similar generic words can place sports chunks alongside SDK chunks. |
| The relevant row is ranked below a large table or is truncated | `tr_20260824_131138_158606`, `tr_20260824_131138_aa8066` | Chunk boundaries and top-k selection do not guarantee that the exact parameter or error row is included in the selected context.                               |

### Current Trace Example

Trace `tr_20260826_141604_f8f24b` asks: `what are the error in the coer data`.

The retriever returned three Core Bluetooth chunks, all from the relevant document:

* Rank 1: `p5:c2`, score `0.3174`
* Rank 2: `p6:c0`, score `0.3081`
* Rank 3: `p5:c1`, score `0.2832`

This is **not a clear document-level retrieval miss**. The chunks mention `CBError`, `CBATTError`, and error codes, so the broad topic was retrieved. The retrieval weakness is that the query is misspelled and vague, and the selected chunks do not provide a complete list of the requested error details.

## Stored Answer Failures

| Failure                                                                        | Evidence                                                                                                           | Reason                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Correct evidence is retrieved but the requested number is absent               | `tr_20260824_131138_c41aed`, `tr_20260824_131138_3b14d5`, `tr_20260824_131138_395aa7`, `tr_20260824_131138_1116f0` | The extractive generator selects nearby sentences instead of checking that every requested field or number appears in the answer.                                                                                  |
| The answer uses a stale v2 value                                               | `tr_20260824_131138_576c5d`                                                                                        | The final answer follows the highest-ranked v2 evidence without resolving the version ambiguity.                                                                                                                   |
| The answer leads with a v2-to-v3 change instead of the requested current value | `tr_20260824_131138_416582`, `tr_20260824_131138_547c7a`                                                           | Extractive selection favors a highly similar historical sentence, and there is no answer-level rule requiring the current value to appear first.                                                                   |
| The answer confidently responds to an unanswerable question                    | `tr_20260824_131138_244ba5`, `tr_20260824_131138_d7cd4c`                                                           | The generator produces an answer whenever chunks exist; it does not require a minimum evidence threshold or verify that the retrieved text actually answers the question.                                          |
| The answer duplicates the same sentence                                        | `tr_20260824_131138_c31a87`, `tr_20260824_131637_f71776`                                                           | Multiple near-duplicate chunks are selected, and the generator does not deduplicate extracted sentences.                                                                                                           |
| The correct fact is buried inside a table or list dump                         | `tr_20260824_131138_5fddc2`, `tr_20260824_131138_8d8b3b`, `tr_20260824_131138_158606`                              | The answer preserves a large source fragment rather than extracting the exact field requested.                                                                                                                     |
| The answer drifts into generic or unrelated context                            | `tr_20260824_131138_59beb9`, `tr_20260824_131138_791fc2`, `tr_20260824_131138_106141`                              | There is no final relevance check, so a second selected chunk can contribute a cover page, generic overview, or contradictory example.                                                                             |
| The current Core Bluetooth answer is incomplete                                | `tr_20260826_141604_f8f24b`                                                                                        | The answer correctly names `CBError` and `CBATTError`, but it does not list the requested error codes or explain the specific errors. Retrieval found broad evidence, but generation stopped at a shallow summary. |

## Failure Summary

The seeded sample contained **19 observable failures across 20 traces**:

| Mode                                | Count | Frequency | Main Reason                                       |
| ----------------------------------- | ----: | --------: | ------------------------------------------------- |
| Stale v2 default                    |     2 |       10% | No SDK-version filtering or ambiguity resolution  |
| Change-log sentence first           |     2 |       10% | Historical text scores highly and is copied first |
| Unrelated answer instead of refusal |     2 |       10% | No evidence threshold or answerability check      |
| Requested number missing            |     4 |       20% | No required-field or question-coverage check      |
| Duplicate sentences                 |     3 |       15% | No deduplication after extraction                 |
| Fact buried or truncated            |     3 |       15% | Table-like chunks are copied as blobs             |
| Second-half drift                   |     3 |       15% | No final relevance or contradiction check         |

The **largest single failure mode** is the omission of the requested value. The **highest-risk retrieval failures** are version mixing and unrelated document retrieval. The **highest-risk stored-answer failure** is confidently presenting an answer when the retrieved evidence does not support the question.

## Recommended Checks

1. Filter SDK retrieval by the requested version. For unversioned SDK questions, default to v3 while leaving non-SDK documents unaffected.

2. Add an evidence threshold and refuse to answer when the retrieved context does not sufficiently support the question.

3. Require the answer to contain the requested field or number before returning it.

4. Deduplicate extracted sentences and reject unrelated second sentences.

5. Preserve `retrieval.latency_ms`, `generation.latency_ms`, and each ranked chunk's `trace_time_ms` so retrieval and answer-generation costs remain visible in every trace.
