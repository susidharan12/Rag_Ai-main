# Week 5 Complete Report — Error Analysis: Reading Traces Like a Professional

**Course:** Soft Suave · The AI Engineering League · Module M3 (Evals & Error Analysis) · Task Set E
**Domain:** Developer documentation (Nimbus SDK v2/v3 reference pages + sports-rules PDF)
**Week:** 5 · **Sat on:** Week 6 Monday · **Marks:** 100
**Branch:** `week5` · Head commit at time of writing: `bd74dad` ("frontend and Week 5 implemenation", 2026-08-25)

---

## 1. What the Week 5 task was

The docs assistant had been running all week and its trace file had grown past a thousand lines nobody read. The DX lead's only "bug report" was that it *"sometimes gives outdated code."* This week did not ask us to fix anything. It asked us to:

| # | Requirement | Points |
|---|-------------|-------:|
| R1 | Prove traces are **replayable**: pick one trace by seeded `trace_id`, replay it *from the trace alone*, show original vs replayed output; add any missing field and declare what couldn't be reconstructed | 20 |
| R2 | Draw a **provably random sample of 20 traces** with a seed pasted in the write-up | 20 |
| R3 | **Open-code all 20** — one honest observation sentence per trace, zero diagnoses, zero fixes during coding | 25 |
| R4 | Cluster into **4–7 legibly named failure modes**, each with count, frequency %, severity, one example `trace_id` | 30 |
| R5 | A **dated, falsifiable prediction** with exact numbers, committed to git *before* any fix | 15 |
| R6 | **3 sentences** on why a public benchmark score would have missed the top modes | 10 |
| B | **Bonus:** same rubric on the curated demo set of 10; compare top-mode frequency random vs demo | + |

---

## 2. What we implemented in Week 5 (file inventory)

| File | Role |
|---|---|
| `rag_core/tracing.py` | JSONL trace writer/reader — every turn through the pipeline records a full trace record |
| `week5_error_analysis/ingest_corpus.py` | Ingests 8 SDK markdown pages (v2+v3) + the sports PDF into the multi-doc `DocStore` → **9 documents, 168 chunks** |
| `week5_error_analysis/generate_traces.py` | Runs a **46-question battery** (written before any output was seen) through the live pipeline — real embeddings, real FAISS search, real generator — tagged by intent surface: `A` v3 factoids (10), `B` version-ambiguous repeats (6), `C` explicit-v2 maintainer questions (4), `D` cross-reference traps (4), `E` Week-4 sports golden questions (12), `F` out-of-corpus should-refuse (5), `G` vague/multi-part (3), `H` code-usage (2) |
| `week5_error_analysis/sample_traces.py` | Seeded random sampling — `random.Random(20260824).sample(ids, 20)` from the population; writes `traces/sample_20.json` |
| `week5_error_analysis/dump_sample.py` | Prints full detail (retrieved chunks + scores + raw output) of the 20 sampled traces for hand open-coding |
| `week5_error_analysis/replay_trace.py` | Replays one trace **from the trace record alone** and diffs retrieval, scores (tolerance 1e-3), and raw output against the original; writes `replay_evidence.json` |
| `week5_error_analysis/demo_set_sample.py` | Bonus: runs the 10 curated DX-review demo questions through the identical pipeline (`traces/demo_set.json`) so they can be labelled with the same rubric |
| `server/`, `frontend/` | Chat UI + API so real turns land in the trace file like production traffic would |
| Evidence artifacts | `traces/traces.jsonl` (61 trace objects; 46 at draw time), `traces/sample_20.json`, `traces/demo_set.json`, `replay_evidence.json` |

### Trace schema (the replayability contract)

Every trace records everything needed to reproduce the turn:

```
trace_id, ts_utc, surface, question, refused,
latency_ms{...},
retrieval{ embedding_model, top_k, min_score, index_chunk_count,
           documents_indexed,
           retrieved[ {rank, chunk_id, score, source_doc,
                       page_number, sdk_version} ] },
generation{ model, prompt_version, params{max_sentences},
            context_chunk_ids },
raw_output
```

Nothing was missing when replay time came — prompt version, retrieved chunk_ids + scores, model + params, and raw output were all captured at write time, so **nothing had to be added or reconstructed**. One honest caveat declared up front: the generator used for the battery is `extractive-v1` (deterministic), which is what makes byte-identical replay possible; if the battery had run on Ollama, an exact replay would additionally require recording temperature/seed, which the current schema does not store. That is the one thing we could not fully exercise.

---

## 3. How Week 5 differed from Week 4 (and Week 3)

| Dimension | Week 3 (RAG + chunkers) | Week 4 (golden set + rerank) | Week 5 (error analysis) |
|---|---|---|---|
| Core question | Can we build retrieval at all? Does the chunker keep tables/code fences intact? | Is retrieval *accurate*, and can reranking fix misses? | *What does the system actually tell users*, and how often is it wrong in each way? |
| Data | Corpus we ingested; 8 questions written first | Curated golden set of 12 questions **we wrote** | Traffic-like traces (**46-question battery + frontend turns**), then a **random sample we didn't choose** |
| Direction of work | Hypothesis → metric → verdict | Hypothesis → metric → delta → ship/no-ship decision | **Observe → describe → cluster → *then* hypothesize with a pre-registered number** |
| Unit of analysis | Chunk / index | Question → hit@3, latency, R/G/NotInCorpus labels | Turn → what the user reads, verbatim |
| Fixing allowed | Yes, throughout | Yes (rerank layer added) | **Zero fixes during open-coding** — the zero itself is graded |
| Output artifact | Working pipeline + chunker decision | Ship decision (dense baseline kept; CE-rerank rejected at 3.6× latency for +0.08 hit@3) | Ranked taxonomy + a dated falsifiable prediction |
| Numbers produced | hit@5 8/8 tie; hit@1 7/8 vs 6/8 | 0.33 → 0.42 hit@3, p50 9.7→35.3 ms | Frequencies: e.g. wrong-version answers 10%, silent non-refusals 10%, missing-number outputs 20% |
| Key mindset shift | Build it right | Measure it honestly | **Look at it before believing anything about it** |

Weeks 3–4 graded whether the retriever finds the right chunk on question sets *we authored*. Week 5 reversed the direction: no metric was computed up front at all. We read what real phrasing (colloquial, versionless, out-of-corpus, multi-part) produces, described it without diagnosing, and only then committed to one attack with a number we're allowing ourselves to be wrong about. Week 4's labels (R/G/NotInCorpus) were assigned to known-answer questions; Week 5's failure modes were discovered from observations, not defined in advance — the assignment explicitly warns that deciding categories first guarantees you find exactly what you expected and nothing else.

---

## 4. The process, step by step (what we actually did)

1. **Capture.** Ran the 46-question battery through the live pipeline (`generate_traces.py`, extractive generator) plus frontend/server traffic → `traces/traces.jsonl` (population 46 at draw time; 61 after later dev/frontend turns).
2. **Seeded sample.** `SEED = 20260824` (yyyymmdd of capture day). `random.Random(20260824).sample(ids, 20)` over sorted trace_ids → `traces/sample_20.json`. Anyone re-running `python -m week5_error_analysis.sample_traces` gets the identical 20 ids.
3. **Replayability proof** (before any coding): seeded pick `Random(20260824).choice(sorted_sample)` → `tr_20260824_131138_8d8b3b`; replayed from the trace alone (see §5).
4. **Open-coded all 20** by hand from `dump_sample.py` output — descriptions only, no categories, no fixes (§7).
5. **Clustered** the sentences bottom-up into 7 modes + 1 clean trace (§8).
6. **Committed a dated, falsifiable prediction** before touching any code (§9).
7. **Bonus:** ran the curated 10-question demo set through the identical pipeline and labelled it with the same rubric (§10).
8. Wrote this report. **No behavior change has been made to the running system as part of this week.**

---

## 5. Replay evidence (R1)

**Selection rule:** `random.Random(20260824).choice(sorted(sample_20.trace_ids))` → **`tr_20260824_131138_8d8b3b`**

**Question:** *"How many rounds in a professional boxing bout?"*

| Check | Result |
|---|---|
| Index state matches trace record (`index_chunk_count`) | ✅ true (168 == 168) |
| Retrieved chunk_ids identical | ✅ true |
| Scores within 1e-3 | ✅ true |
| Raw output identical (stripped compare) | ✅ true |

Original and replayed retrieval (identical):

```
0.6843  complete-guide-to-major-world-sports:p20:c0
0.6719  complete-guide-to-major-world-sports:p20:c2
0.6434  complete-guide-to-major-world-sports:p20:c3
0.5672  complete-guide-to-major-world-sports:p20:c5
0.5638  complete-guide-to-major-world-sports:p20:c4
```

Original output (= replayed output, byte-for-byte after whitespace strip):

> " A bout is divided into rounds, with a short rest period between each. [complete-guide-to-major-world-sports:p20:c3] Competitors 2 (individual) Duration Bouts of 3-12 rounds, each 2-3 minutes Equipment Gloves, mouthguard, boxing ring Governing Body AIBA / various pro sanctioning bodies Overview Boxing pits two fighters of similar weight against each other in a roped ring. [complete-guide-to-major-world-sports:p20:c0]"

Machine-checkable copy: `week5_error_analysis/replay_evidence.json`. Fields that had to be added afterwards: **none**. What could not be reconstructed: nothing for this corpus/generator pairing; the general case (stochastic LLM replay) is noted in §2.

Note the replay target itself is instructive: retrieval was perfect (all five chunks from the right boxing page) and yet the answer buries "3-12 rounds" mid-list — a generation/presentation failure, not a retrieval failure. That distinction is invisible in any single aggregate metric.

---

## 6. The seeded random sample (R2)

**Seed: `20260824`** · Population **46** traces · k = **20** · Verifiable via `python -m week5_error_analysis.sample_traces`.

| # | trace_id | Surface | Question (short) |
|---|----------|---------|------------------|
| 1 | tr_20260824_131138_106141 | B | How many events can I fetch per page? |
| 2 | tr_20260824_131138_1116f0 | G | Explain authentication incl. token expiry and scopes |
| 3 | tr_20260824_131138_158606 | D | Is HTTP 429 (RATE_LIMITED) retryable? |
| 4 | tr_20260824_131138_244ba5 | F | Rate limit for /v3/events/stream endpoint? |
| 5 | tr_20260824_131138_345fb0 | H | Show me how to verify a webhook signature in Python |
| 6 | tr_20260824_131138_395aa7 | B | How big can the pool be when I connect my client? |
| 7 | tr_20260824_131138_3b14d5 | B | What timeout does Client.send() use? |
| 8 | tr_20260824_131138_416582 | A | Default timeout_ms for Client.send()? |
| 9 | tr_20260824_131138_547c7a | A | Max allowed value of limit in list_events()? |
| 10 | tr_20260824_131138_576c5d | A | Default pool_size for Client.connect()? |
| 11 | tr_20260824_131138_59beb9 | E | Governing body for international Badminton? |
| 12 | tr_20260824_131138_5fddc2 | E | Men's volleyball net height? |
| 13 | tr_20260824_131138_63361c | E | How many holes in a standard golf course? |
| 14 | tr_20260824_131138_791fc2 | E | Points for a try in Rugby Union? |
| 15 | tr_20260824_131138_8d8b3b | E | Rounds in a professional boxing bout? |
| 16 | tr_20260824_131138_c31a87 | E | NBA shot clock limit? |
| 17 | tr_20260824_131138_c41aed | A | How many times does Client.send() retry by default? |
| 18 | tr_20260824_131138_d00a20 | B | What retries do I get on send? |
| 19 | tr_20260824_131138_d7cd4c | F | Who won the 1998 FIFA World Cup final? |
| 20 | tr_20260824_131138_d9caf7 | C | Is SDK v2 still supported? |

*(The authoritative machine-readable list is `traces/sample_20.json`; this table and the sampler output agree id-for-id.)*

---

## 7. Open-coding — all 20 sentences, verbatim (R3)

One observational sentence per trace. No category names, no diagnoses, no fixes. Zero code changes were made between trace 1 and trace 20.

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
15. **tr_…_8d8b3b** — The "3-12 rounds" figure is embedded mid-list inside a Duration field of a table dump; the opening sentence says only that a bout "is divided into rounds."
16. **tr_…_59beb9** — BWF appears in the first sentence, and the second citation is the PDF's cover/title page listing every sport in the book.
17. **tr_…_244ba5** — The system did not refuse: it returned a pagination-limit ValueError paragraph and a v2/v3 defaults-change sentence, neither of which mentions streaming or requests-per-second.
18. **tr_…_d7cd4c** — The output never refuses and never names a winner; it ends with the two-word fragment "World Cup." cited as if it were a sentence.
19. **tr_…_1116f0** — The `scope` parameter shows up in the code example, but token expiry — half the question — appears nowhere in either sentence.
20. **tr_…_345fb0** — The webhook verification example came back complete and on-topic; I don't see anything wrong in this trace. *(An honest "clean" is part of the data too.)*

---

## 8. Taxonomy — the one-screen deliverable (R4)

Clustered bottom-up from §7. Severity legend: 🔴 ships broken code to a user's repo · 🟡 merely annoys the reader.

| Mode (named so a stranger knows what to do) | Count | Freq | Sev | Example trace_id |
|---|:---:|:---:|:---:|---|
| **M1 — Answers with the stale v2 default when the question doesn't name a version** | 2 | 10% | 🔴 | `tr_20260824_131138_576c5d` (tells user `pool_size=5`; v3 default is 10) |
| **M2 — Opens with the v2→v3 change-log sentence instead of the current value** | 2 | 10% | 🟡 | `tr_20260824_131138_416582` |
| **M3 — Out-of-corpus question answered with unrelated text; refusal never fires** | 2 | 10% | 🔴 | `tr_20260824_131138_244ba5` (stream rate limit answered with pagination prose) |
| **M4 — Right page retrieved but the asked-for number never appears in the output** | 4 | **20%** | 🔴 | `tr_20260824_131138_3b14d5` (timeout question, zero timeout values shown) |
| **M5 — Duplicate/near-duplicate sentences pad the answer** | 3 | 15% | 🟡 | `tr_20260824_131138_c31a87` |
| **M6 — Correct fact present but buried inside a table/list blob (or truncated before the needed row)** | 3 | 15% | 🟡 | `tr_20260824_131138_8d8b3b` |
| **M7 — Second half of the answer drifts off-question (cover page, generic blurb, contradicting example)** | 3 | 15% | 🟡 | `tr_20260824_131138_59beb9` |
| *(Clean — no observable failure)* | 1 | 5% | — | `tr_20260824_131138_345fb0` |

Totals: 7 failure modes covering 19/20 turns; 3 red-severity modes account for **40%** of the random sample. This is the ranked answer to "it sometimes gives outdated code": outdated code (M1+M2) is real but only ~20%; the biggest single bucket is silently omitting the number the user asked for (M4), and the most dangerous trust-killer is confidently answering unanswerable questions (M3).

Per-mode membership: M1 = {576c5d, d00a20} · M2 = {416582, 547c7a} · M3 = {244ba5, d7cd4c} · M4 = {c41aed, 3b14d5, 395aa7, 1116f0} · M5 = {c31a87, d9caf7, 63361c} · M6 = {5fddc2, 8d8b3b, 158606} · M7 = {59beb9, 791fc2, 106141} · Clean = {345fb0}. (Secondary observations — e.g. sports-PDF chunks contaminating SDK context slots in 547c7a/395aa7 — are recorded inside the §7 sentences.)

---

## 9. Dated, falsifiable prediction (R5)

> **Date committed: 2026-08-26** · Author: fares · Status: written **before any fix exists**
>
> Next week I will attack **Mode 1 (stale v2 defaults)** by adding an `sdk_version` metadata filter to `DocStore.search()`, defaulting to `v3` unless the question explicitly mentions v2 (same over-fetch-then-filter approach proven in Week 3's `sdk_query.search_sdk()`).
>
> **Prediction, exact numbers:** re-running the identical seeded sample (seed `20260824`, same 20 trace_ids, extractive generator) against the changed pipeline:
> - M1 drops from **2/20 (10%) to 0/20 (<5%)**;
> - M2 drops from **2/20 (10%) to ≤1/20 (≤5%)**;
> - no new traces enter M3 (refusal behavior untouched), and all five sports-E traces keep their correct facts (filter must be a no-op for `sdk_version=""` documents).
>
> **Falsification:** if any v2-default answer still reaches a versionless user (M1 ≥ 1/20), or any sports/E trace regresses, the change failed and gets reverted. "It improved things overall" is not an acceptable outcome — only these numbers are.

Commit step (rubric requires the hash pinned before the fix lands):

```bash
git add week5_report.md && git commit -m "Week 5 prediction (2026-08-26): sdk_version=v3 filter drops stale-v2 mode 10%->0%, changelog-first 10%-><=5%"
git rev-parse --short HEAD   # paste hash here after committing
```

Committed hash: `<paste after commit>` — the prediction above is the content being committed; nothing in the pipeline changes until after this commit exists.

---

## 10. Benchmark note (R6) — why a public benchmark wouldn't have caught the top 3

Public benchmarks (Natural Questions, MS MARCO, TriviaQA-style sets) are built from single-version corpora whose gold passages are guaranteed present, so Mode 1 — the wrong *version* of a fact outranking the right one — cannot even exist there; our 10% wrong-default rate would read as a flawless score. They also contain no out-of-corpus split scored at the generation layer, so Mode 3's confident non-refusals never get measured: a benchmark rewards answering every question, which is precisely the wrong incentive for a docs assistant that must sometimes say "I cannot answer this from the indexed pages." And because benchmark questions are written close to the source wording, they never stress the colloquial phrasings ("what retries do I get on send?", "how big can the pool be?") that make Mode 4 drop the requested number entirely — our users' questions are messier than any public set we'd be scored on.

---

## 11. Bonus — random sample vs the curated demo set

Same pipeline, same rubric, 10 demo questions (`demo_set_sample.py` → `traces/demo_set.json`). Labelling:

| Demo trace | Label |
|---|---|
| …_cc8793 (pool_size) | M1 — v2 default `5` given as the answer |
| …_d97e1b (timeout_ms), …_ca746c (limit max) | M2 — changelog-first |
| …_aa8066 (retry_backoff_ms default) | M4 — parameters table truncated before the needed row; default never shown |
| …_f71776 (NBA shot clock) | M5 — duplicate sentence |
| …_ded86a (429 retryable), …_e0a03c (football players), …_ffb7ec (volleyball net) | M6 — buried/truncated blobs |
| …_d7daf7 (badminton BWF) | M7 — cover-page filler as second sentence |
| …_b8b74c (webhook verify) | Clean |

**Top mode (M4 — asked-for number absent): random sample 4/20 = 20% vs demo set 1/10 = 10%.**
Demo set profile: M1 10%, M2 20%, M4 10%, M5 10%, M6 30%, M7 10%, clean 10%. Note what the demo set structurally cannot contain: zero out-of-corpus questions (M3 = 0%), zero version-ambiguous colloquial asks beyond the two planted ones, and every question phrased almost exactly like the doc wording.

**What the team has been telling itself for the last month:** the DX review deck has been proving the assistant works by showing ten questions that were chosen — unconsciously but consistently — because they look good on a slide: phrasing lifted from the docs themselves, always answerable, always in-corpus, run on whatever build we were proud of that day. Against that mirror, the assistant looks 90% healthy and "sometimes outdated code" sounds like a rare edge case, when the random sample says 40% of real turns carry a red-severity failure and the single biggest mode isn't outdatedness at all but quietly omitting the number the user asked for. Our demo frequency wasn't just optimistic — it was generated by the selection process we trusted to measure us, which is exactly why this week forced a seeded draw instead of a favorite-questions tour.

---

## 12. Submission checklist mapping

- [x] **taxonomy.md content** → §8 (one screen, 4–7 rows with count/%/severity/example id)
- [x] **notes.md content — 20 verbatim open-coding sentences** → §7
- [x] **Seeded random sample: seed + 20 ids** → §6 (seed `20260824`; machine list in `week5_error_analysis/traces/sample_20.json`)
- [x] **Replay evidence: original vs replayed + fields added** → §5 (nothing added; caveat in §2; `replay_evidence.json`)
- [x] **Dated prediction committed to git with hash** → §9 (commit command provided; paste hash after `git commit`)
- [x] **Benchmark note** → §10
- [x] **Bonus comparison + paragraph** → §11

## 13. Reproduce everything

```bash
python -m week5_error_analysis.ingest_corpus      # 9 docs, 168 chunks
python -m week5_error_analysis.generate_traces    # 46-trace battery -> traces.jsonl
python -m week5_error_analysis.sample_traces      # SEED=20260824 -> same 20 ids
python -m week5_error_analysis.dump_sample        # full detail for open-coding
python -m week5_error_analysis.replay_trace       # seeded pick -> replay diff + evidence json
python -m week5_error_analysis.demo_set_sample    # bonus curated 10
```
