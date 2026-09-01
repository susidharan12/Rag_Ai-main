# Week 5 — Trace Observations, Failures & Chunking Problems

Raw, structured notes compiled from the seeded sample (`sample_20.json`), the failure
analysis (`failure_analysis.md`), and the retrieval/storing investigation
(`retrieval_and_storing_failures.md`). Observations are kept descriptive; diagnoses
and fixes are separated into their own sections.

---

## 1. Per-Trace Observations (open-coded, 20 sentences verbatim)

One observational sentence per trace. No categories, no fixes.

1. **tr_…_416582** — The output's first sentence reports the v2→v3 timeout *change* ("30000 halved to 15000") rather than stating a single current default, and its second sentence describes what `Client.send()` does, not any timeout.
2. **tr_…_c41aed** — Neither sentence states how many times `send()` retries; both are "Notes" paragraphs mentioning `max_retries` without ever giving its value.
3. **tr_…_576c5d** — The output quotes only the **v2** `pool_size` default of `5` (prose plus a v2 code sample); the number `10` never appears even though the question named no version.
4. **tr_…_547c7a** — The answer opens with the v2→v3 limit history ("was 100, raised to 200"), then shows a code example passing `limit=100`, and the last two retrieved chunks are sports-PDF pages.
5. **tr_…_3b14d5** — No timeout value of any kind appears in the output; the first sentence is the v2 maintenance-mode banner and the second is a note about 429 retries.
6. **tr_…_395aa7** — The output is two near-identical one-line descriptions of `Client.connect()` from the v3 and v2 pages; no pool-size number appears anywhere, and a sports-PDF chunk sits at rank 5.
7. **tr_…_106141** — The output shows an example using `limit=100` immediately followed by a table row saying the default is `50` with accepted range 1–200, so two different numbers are on screen with nothing reconciling them.
8. **tr_…_d00a20** — The output pairs a v3 errors-note about retryable codes with a **v2** parameter row showing `retry_backoff_ms | int | 250`, and never states the retry count.
9. **tr_…_d9caf7** — Both sentences of the output are the identical "v2 is in maintenance mode" banner, quoted once from the connect page and once from the send page.
10. **tr_…_158606** — The quoted codes table begins at the `400 INVALID_ARGUMENT` row and stops before reaching the `429` row, so the `yes` that answers the question is never shown; the second sentence is client_send prose that merely mentions 429.
11. **tr_…_c31a87** — The correct 24-seconds sentence appears twice in a row, cited to two different chunks (`p7:c3` and `p7:c2`).
12. **tr_…_791fc2** — The first sentence gives "5 points" correctly; the second is the generic Rugby (Union) overview blurb, which says nothing about scoring.
13. **tr_…_5fddc2** — The men's net height appears only inside a packed equipment list ("net (2.43 m men's / 2.24 m women's)"); every surrounding sentence is about players, sets, and the governing body.
14. **tr_…_63361c** — "Typically 18 holes" arrives inside a Players/Course/Equipment/Governing-Body block, then the second sentence repeats the same overview text again.
15. **tr_…_8d8b3b** — The "3-12 rounds" figure is embedded mid-list inside a Duration field of a table dump; the opening sentence says only that a chance "is divided into rounds."
16. **tr_…_59beb9** — BWF appears in the first sentence, and the second citation is the PDF's cover/title page listing every sport in the book.
17. **tr_…_244ba5** — The system did not refuse: it returned a pagination-limit ValueError paragraph and a v2/v3 defaults-change sentence, neither of which mentions streaming or requests-per-second.
18. **tr_…_d7cd4c** — The output never refuses and never names a winner; it ends with the two-word fragment "World Cup." cited as if it were a sentence.
19. **tr_…_1116f0** — The `scope` parameter shows up in the code example, but token expiry — half the question — appears nowhere in either sentence.
20. **tr_…_345fb0** — The webhook verification example came back complete and on-topic; nothing wrong observed. *(Honest "clean" is part of the data too.)*

Additional current-trace observation:
- **tr_20260826_141604_f8f24b** — Misspelled, vague query "what are the error in the coer data" retrieved three Core Bluetooth chunks (broad topic found) but the answer only names `CBError`/`CBATTError` and never lists the requested error codes.

---

## 2. Observed Failure Modes (taxonomy summary)

| Mode | Count | Freq | Sev | Example |
|---|:---:|:---:|:---:|---|
| M1 Stale v2 default for versionless question | 2 | 10% | 🔴 | `576c5d` |
| M2 Change-log sentence first | 2 | 10% | 🟡 | `416582` |
| M3 Out-of-corpus answered, no refusal | 2 | 10% | 🔴 | `244ba5` |
| M4 Requested number missing | 4 | 20% | 🔴 | `3b14d5` |
| M5 Duplicate/near-duplicate sentences | 3 | 15% | 🟡 | `c31a87` |
| M6 Fact buried in table/list blob | 3 | 15% | 🟡 | `8d8b3b` |
| M7 Second-half drift off-question | 3 | 15% | 🟡 | `59beb9` |
| Clean | 1 | 5% | — | `345fb0` |

3 red-severity modes = 40% of the random sample. Full table in `taxonomy.md`.

---

## 3. Chunking Problems

### C1. Page-boundary blindness
- **What:** Questions whose answer spans two pages cannot be answered even when both pages are indexed; retrieval returns only chunks from one page.
- **Why:** `chunk_pages()` (chunker.py:47) chunks **per page independently** — the algorithm never crosses a page break. A sentence continuing from p7 to p8 lives in two separate vectors; a query matching only the p8 continuation gets zero hits.
- **Impact:** Cross-page answers are structurally unretrievable.

### C2. 50% of the index is duplicated text (overlap inflation)
- **What:** With `CHUNK_SIZE=500, CHUNK_OVERLAP=250`, every chunk shares ~250 chars of tail-text with its successor.
- **Why:** The overlap loop (chunker.py:28-35) copies tail words of each chunk into the next; each pair overlaps 250/500 ≈ 50%.
- **Impact:** Near-duplicate chunks get near-identical vectors → they occupy multiple rank slots for one query (NBA trace had p7:c3 and p7:c2 containing the identical shot-clock sentence), wasting retrieval slots and showing duplicate sources to the user.

### C3. Relevant row truncated / buried by table-shaped chunks
- **What:** A parameter or error row that answers the question sits at the boundary of a table-shaped chunk and is never surfaced (e.g., `158606` stops before the `429` row; `aa8066` truncates before the retry default).
- **Why:** Chunk boundaries cut tables arbitrarily; top-k selection doesn't guarantee the exact row is in the selected context.
- **Impact:** Right page retrieved, but the asked-for number is absent (M4 / M6).

### C4. No re-merge of continuation chunks / no heading hierarchy tracking
- The chunker was inherited from Week 3 where pages were natural semantic units; nothing re-merges continuation chunks or tracks heading hierarchy across boundaries.

---

## 4. Retrieval Failures

### R1. Noise-floor threshold admits irrelevant chunks
- `all-MiniLM-L6-v2` embeddings are anisotropic: all vectors cluster in a narrow cone, so *any* two English texts share baseline cosine ≈0.12–0.14 regardless of topic. `MIN_SCORE=0.12` sits *inside* that noise band (e.g., "who is akash" → handball chunk at 0.127). No relative/exponential cutoff is applied despite a massive cliff between rank 1 (0.417) and rank 2 (0.127).

### R2. `top_k` silently starves and ranks get corrupted
- `store.py:237` filters `score < min_score` *after* the `enumerate()` loop that assigns `rank` (store.py:236). If rank 2 is filtered, survivors keep their original indices → ranks 1 and 3 appear, with no `"filtered_out"`/`"starved"` signal.

### R3. Page-boundary blindness — *see C1 above.*

### R4. 50% duplicated text in index — *see C2 above.*

### R5. Dense-only retrieval hard ceiling on exact-token questions
- Week 4 baseline hit@3 = **0.33** (4/??) wait: 4/12 golden; cross-encoder rerank only reached 0.42 at 3.6× latency and was rejected.
- Questions hinging on exact tokens — numbers, codes, acronyms — fail because a 384-dim vector compresses away precise lexical content ("24 seconds", "BWF", "429 RATE_LIMITED"). The G7 governing-body chunk ranked global 9; G2's shot-clock chunk at rank 142.
- Prose mentioning "429 RATE_LIMITED" outranked the authoritative errors table row.
- No BM25/keyword index exists anywhere in rag_core; no second signal to fuse with.

---

## 5. Storing / Persistence Failures

### S1. Non-atomic saves — crash corrupts the entire index
- `_save()` (store.py:92-100) writes directly onto `chunks.pkl`, then separately writes `registry.json`. No temp-file + atomic rename. Crash between writes → corrupted/unpicklable index, dead app on next startup.

### S2. Duplicate filenames produce colliding `chunk_id`s
- `doc_id` gets a UUID suffix (store.py:127) but `chunk_id` is built only from filename slug + page + index (store.py:155). Upload `report.pdf` twice → chunks share IDs like `report:p1:c0`. Citations `[report:p1:c0]` become ambiguous.

### S3. `vector_offset` metadata goes stale after deletes
- `delete_document()` compacts arrays (store.py:187-193) but **never updates survivors' offsets**. Any consumer trusting `vector_offset` reads another document's vectors.

### S4. Every mutation rewrites the entire corpus
- One 2-page upload → `np.vstack` copies the whole embedding matrix, `pickle.dump` serializes *all* chunks, FAISS rebuilt from scratch. Sequential uploads → O(n²)-ish total work; latency grows with corpus size.

### S5. Pickle as persistence format
- `chunks.pkl` loaded with bare `pickle.load` (store.py:78): (a) security — tampered `.pkl` executes arbitrary code; (b) lock-in — decodes only with matching class/numpy versions; (c) uninspectable — can't grep/debug like JSON/parquet.

### S6. Unresolved git merge conflict in `results.md`
- `results.md` line 283 still contains raw conflict markers (`<<<<<<< HEAD` … `>>>>>>> week4`). Week 4 → main merge never completed; breaks rendering after §8.

---

## 6. Synthesis

The Week 3 prototypes solved four problems correctly (version filter, citation resolution,
refusal prompts, structured chunking) but as throwaway scripts. The rag_core production path
inherited only the simplest parts. The complex problem underneath everything is **the gap
between what was proven in prototype scripts and what shipped into the production pipeline**.
All measured failures (C1–C4, R1–R5, S1–S6, M1–M7) stem from that same architectural debt:
retrieval and storage logics cobbled from Week 3 experiments without the evaluation harness,
schema discipline, or engineering rigor a production RAG system needs.

---

## 7. Latest Update — Prompt Version Configuration

The pipeline previously carried **two** prompt-version constants:

- `PROMPT_VERSION_LLM = "grounded-strict-v2"` (Groq generator)
- `PROMPT_VERSION_EXTRACTIVE = "extractive-grounded-v1"` (extractive generator)

These were collapsed into a **single, env-configurable `PROMPT_VERSION`** (default `"v1"`)
in `rag_core/settings.py`:

```python
DEFAULT_GENERATOR = os.environ.get("RAG_GENERATOR", "groq")
PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "v1")
```

Both `generate_groq` and `generate_extractive` now report `settings.PROMPT_VERSION` in their
trace records (previously split across `PROMPT_VERSION_LLM` / `PROMPT_VERSION_EXTRACTIVE`).

**Effect on traces:** every generated turn now tags `generation.prompt_version` with the
single active value. To switch prompt versions later (e.g. back to v2), set `PROMPT_VERSION`
in `.env` or the environment — no code change required. New traces will record the new version,
so version-based filtering/replay stays consistent across both generators. This is the latest
change and is reflected in `taxonomy.md` as well.
