# Retrieval and Storing Failures — Detailed Investigation

## 1. Retrieval Failures

### R1. Noise-floor threshold admits irrelevant chunks
- **What:** Unrelated chunks enter the LLM context (e.g., "who is akash" → handball rules chunk at score 0.127).
- **Reason:** `all-MiniLM-L6-v2` embeddings exhibit anisotropy: all vectors cluster in a narrow cone, so *any* two English texts share baseline cosine similarity ≈0.12–0.14 regardless of topic. Your `MIN_SCORE=0.12` sits *inside* that noise band; rank-2 handball chunk cleared it by 0.007 above threshold.
- **Why it happens:** The constant was chosen as an arbitrary floor, never calibrated against the model's measured noise distribution. No relative/exponential cutoff is applied despite a massive score cliff between rank 1 (0.417) and rank 2 (0.127) in the same trace.

### R2. `top_k` silently starves and ranks get corrupted
- **What:** Query asks for 3 chunks, returns 2 with no signal anything dropped; `rank` field becomes non-contiguous (e.g., 1 then 3).
- **Reason:** `store.py:237` filters `score < min_score` *after* the `enumerate()` loop that assigns `rank` (store.py:236). If rank 2 is filtered out, surviving results keep their original enumerate indices → ranks 1 and 3 appear.
- **Why it happens:** The search function never reports how many candidates were discarded; payload lacks any `"filtered_out"` or `"starved"` field, so callers cannot distinguish "only 2 relevant chunks exist" from "retriever bug."

### R3. Page-boundary blindness in chunking
- **What:** Questions whose answer spans two pages cannot be answered even when both pages are indexed; retrieval returns only chunks from one page.
- **Reason:** `chunk_pages()` (chunker.py:47) chunks **per page independently** — the algorithm never crosses a page break. A sentence that physically continues from p7 to p8 lives in two separate vectors; a query matching only the p8 continuation gets zero hits.
- **Why it happens:** The chunker was inherited from Week 3 where pages were natural semantic units; nothing re-merges continuation chunks or tracks heading hierarchy across page boundaries.

### R4. 50% of the index is duplicated text
- **What:** With `CHUNK_SIZE=500, CHUNK_OVERLAP=250` every chunk shares ~250 characters of tail-text with its successor, inflating apparent relevance.
- **Reason:** The overlap loop (chunker.py:28-35) copies the tail words of each chunk into the next; mathematically each pair overlaps 250/500 ≈ 50% of its content.
- **Why it hurts:** Near-duplicate chunks get near-identical vectors → they occupy multiple rank slots for one query (your NBA trace had p7:c3 and p7:c2 containing the identical shot-clock sentence), wasting retrieval slots and showing duplicated sources to the user.

### R5. Dense-only retrieval has a hard ceiling on exact-token questions
- **Measured:** Week 4 baseline hit@3 = **0.33** (4/12 golden-set questions); cross-encoder rerank only reached 0.42 at 3.6× latency and was rejected.
- **What:** Questions hinging on exact tokens — numbers, codes, acronyms — fail because a single 384-dim vector compresses away precise lexical content (e.g., "24 seconds", "BWF", "429 RATE_LIMITED"). The G7 governing-body chunk ranked global 9; G2's shot-clock chunk at rank 142.
- **Related collision:** Prose mentioning "429 RATE_LIMITED" outranked the authoritative errors table row, because embeddings reward natural-language overlap over terse structured truth.
- **Why it's complex:** No BM25/keyword index exists anywhere in rag_core; there is literally no second retrieval signal to fuse with. Fix requires a hybrid system + rank fusion + reranker, and the experiment proved the naive reranker trade-off fails the latency budget.

## 2. Storing / Persistence Failures

### S1. Non-atomic saves — a crash corrupts the entire index
- **What:** If the process dies mid-`_save()`, `chunks.pkl` becomes a truncated, unpicklable file → the entire app is dead on next startup.
- **Reason:** `_save()` (store.py:92-100) writes directly onto `chunks.pkl`, then separately writes `registry.json`. No temp-file + atomic rename pattern.
- **Why it matters:** Crash between the two writes → registry lists a doc whose chunks don't exist, or vice versa. Both files are the *only* copies of the data (uploads are not re-ingestible from original PDFs; ocr_cache.pkl is similarly vulnerable).

### S2. Duplicate filenames produce colliding `chunk_id`s
- **What:** Upload `report.pdf`, edit it, upload again → two documents, and their chunks share identical IDs like `report:p1:c0`.
- **Reason:** `doc_id` gets a UUID suffix (store.py:127) but `chunk_id` is built only from the filename slug + page + index (store.py:155) — uniqueness stops at the document level.
- **Why it matters:** LLM citations `[report:p1:c0]` become ambiguous, dedupe logic downstream can't tell which doc a citation refers to, and trace analysis misattributes chunks.

### S3. `vector_offset` metadata goes stale after deletes
- **What:** Each doc stores its `vector_offset` into the embeddings matrix (store.py:174). `delete_document()` compacts the arrays (store.py:187-193) but **never updates survivors' offsets**.
- **Reason:** Delete re-filters lists positionally; offsets recorded at insert time are never recomputed.
- **Why:** Any consumer trusting `vector_offset` reads another document's vectors. Currently it's unused-but-exported metadata — a landmine rather than an active fire.

### S4. Every mutation rewrites the entire corpus
- **What:** One small 2-page upload → `np.vstack` copies the whole embedding matrix; `pickle.dump` serializes *all* chunks; FAISS rebuilt from scratch.
- **Reason:** Flat-file architecture with full-state rewrite semantics; the threading lock protects threads, not cost.
- **Why it hurts:** Sequential `/api/documents` uploads (api.js loops per file) → O(n²)-ish total serialization work; latency grows linearly with corpus size per upload. 50 files → noticeable per-file latency growth.

### S5. Pickle as persistence format
- **What:** All chunks + embeddings live in `chunks.pkl`, loaded with bare `pickle.load` (store.py:78).
- **Reason:** Fast to build, zero schema work.
- **Why it's a failure mode:** (a) Security — a tampered/swapped `.pkl` executes arbitrary code on load; (b) Format lock-in — decodes only with matching class/numpy versions, no forward compatibility; (c) Uninspectable — you can't grep/debug the index like JSON/parquet.

### S6. Unresolved git merge conflict in results.md
- **What:** `results.md` line 283 still contains raw conflict markers:
  ```
  <<<<<<< HEAD
  =======
  >>>>>>> week4
  ```
- **Reason:** Week 4 → main merge was never completed properly.
- **Impact:** Anyone rendering `results.md` sees broken markdown after §8; repo integrity issue.

## 3. Synthesis: The Gap Between Proven and Shipped

Your Week 3 prototypes solved four problems correctly (version filter, citation resolution, refusal prompts, structured chunking) but in throwaway scripts (`sdk_query.py`, `sdk_generate_eval.py`). The rag_core production path inherited only the simplest parts. The complex problem underneath everything is **the gap between what was proven in prototype scripts and what shipped into the production pipeline** — version filtering, citation verification, and structured chunking all exist as throwaway proofs, not as integrated subsystems.

All measured failures (C1–C6 from the earlier investigation, R1–S6 above) stem from that same architectural debt: retrieval and storage logics were cobbled from Week 3 experiments without the evaluation harness, schema discipline, or engineering rigor needed for a production RAG system.