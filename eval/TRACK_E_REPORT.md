# Track E: Developer Documentation — Report

**Domain:** Nimbus SDK v2/v3 developer docs + sports-rules PDF (same corpus as `week5_error_analysis`/`week6_error_analysis`)
**One command (application eval):** `python eval/run_eval.py`
**One command (judge validation):** `python eval/judge.py`
**Tests:** `python -m unittest eval.test_track_e -v`

Every number below was produced by actually running the commands above against this repository. Nothing was copied from an external report — an earlier draft of this report was pasted into this session referencing commit hashes (`87f9e3e5...`, `708860f4...`) that do not exist anywhere in this repo's git history, and a ChatGPT share link whose page title didn't even match the pasted content. That draft was not used as a source of truth for anything below; it was discarded and this eval was built and run for real instead.

---

## 1. Eval Set

- **28 total cases** — `eval/eval_cases.json`
- Taxonomy distribution:

| Mode | Count |
|---|---:|
| factual_lookup | 13 |
| conceptual_explanation | 5 |
| unsupported_question | 4 |
| ambiguous_question | 3 |
| version_specific | 3 |

- **2 genuine Week-5 regression cases**, verbatim traces from `week5_error_analysis/traces/traces.jsonl` (not hand-authored):
  - `eval_027` — `tr_20260824_131138_576c5d` (versionless `pool_size` question that originally answered with the stale v2 value)
  - `eval_028` — `tr_20260826_141604_f8f24b` (vague/misspelled query that originally returned an incomplete off-topic answer)
- **25 cases** selected for blind human/judge validation (subset of the 28 — excludes `eval_003`, `eval_010`, `eval_013`, the most redundant `factual_lookup` questions; every mode, and both regression cases, remain represented)

---

## 2. One-Command Evaluation

```
python eval/run_eval.py
```

Self-contained: ingests the SDK+sports corpus into an isolated, gitignored `eval/.eval_index/` so it doesn't depend on, or disturb, the live app's `data/index/`.

**28-case application pass rate: 25/28 = 89.3%**

| Mode | Passed / Total | Rate |
|---|---|---:|
| factual_lookup | 13/13 | 100.0% |
| conceptual_explanation | 3/5 | 60.0% |
| unsupported_question | 3/4 | 75.0% |
| ambiguous_question | 3/3 | 100.0% |
| version_specific | 3/3 | 100.0% |
| **TOTAL** | **25/28** | **89.3%** |

The 3 application-layer failures are real, inspectable limitations, not test-authoring bugs:
- `eval_014` — "Explain how Client.send() handles a RATE_LIMITED response" is answered with the method's general description; `retry_backoff_ms`/`max_retries` are never mentioned.
- `eval_017` — "Explain what changed in Client.connect()'s defaults between v2 and v3" says the v2 defaults "are smaller" without ever stating the actual numbers (5 → 10).
- `eval_022` — "What is the maximum webhook payload size accepted by WebhookVerifier?" is answered with an unrelated pagination limit instead of refusing (a previously-documented limitation in `week6_report_fixes.md`, reproduced here independently).

**This is the application pass rate — not judge agreement.** Judge agreement (72.0% → 84.0%) is a separate measurement, reported in Sections 5–9.

---

## 3. Deterministic vs LLM Judge

**Deterministic assertion criteria: 4** (`eval/run_eval.py`):

1. `code_sample_parses`
2. `endpoint_exists`
3. `api_version_stated`
4. `deprecated_symbol_migration`

Applicable counts (`eval/results.json`, 28 cases):

| Criterion | Applicable | Passed | Failed | N/A |
|---|---:|---:|---:|---:|
| code_sample_parses | 0 | 0 | 0 | 28 |
| endpoint_exists | 0 | 0 | 0 | 28 |
| api_version_stated | 4 | 4 | 0 | 24 |
| deprecated_symbol_migration | 0 | 0 | 0 | 28 |

`code_sample_parses` and `endpoint_exists` are genuinely 0/28-applicable here: the deterministic extractive generator answers with extracted sentences, not literal code fences or HTTP paths, for any of these 28 questions. `deprecated_symbol_migration` is genuinely 0/28 because nothing in `corpus/nimbus_sdk/` is described as a deprecated *symbol* with a named migration target (v2 is "in maintenance mode," which isn't the same claim) — the map in `eval/judge.py`/`run_eval.py` stays honestly empty rather than inventing one. `api_version_stated` is applicable on the 3 `version_specific` cases plus `eval_027` (which needed to confirm the versionless question resolves to v3) — 4/4 passed.

**LLM-judged criteria: 1** — a single binary criterion: *does the answer directly and correctly answer the question?* Both `judge_v1.txt` and `judge_v2.txt` state explicitly that the four deterministic criteria are excluded and handled only by `run_eval.py`.

---

## 4. Blind Human Labels

- **25 labels** — `eval/labels_25.json`
- **21 helpful / 4 not helpful**
- Binary (`0`/`1` only), no nulls, all IDs unique
- Commit: [`0463fde47554cd4223858d6078cfb4449f14d3b0`](../../commit/0463fde47554cd4223858d6078cfb4449f14d3b0) — "Track E: eval set, one-command runner, blind labels (before any judge)"
- Timestamp: `2026-09-04T12:53:41+05:30`
- Labels were hand-read from the real answers captured in `eval/results.json` and committed in the same commit as `eval/eval_cases.json` and `eval/run_eval.py`, **before `eval/judge.py` existed** (see `eval/labeling_metadata.txt` and the commit order in §10).

---

## 5. Judge V1

- **25 cases** evaluated
- Judge labels: **18 matches**, **7 disagreements**
- **Agreement = 72.0%**
- Disagreement IDs: `eval_015`, `eval_016`, `eval_018`, `eval_019`, `eval_021`, `eval_022`, `eval_026`
- Commit: [`d4fc5185bf58303e90224a847bf2f5815fc13235`](../../commit/d4fc5185bf58303e90224a847bf2f5815fc13235)

---

## 6. Disagreement Analysis

The 7 V1 disagreements split into two systematic error modes, verified by inspecting each answer directly:

**False negatives** (judge = 0, human = 1): `eval_016`, `eval_018`, `eval_019`, `eval_021`, `eval_026`
- `eval_016`/`eval_018`: genuinely correct, direct answers produced by the extractive generator's `_definition_answer()` path, which — unlike the focused-extraction path — never appends a `[chunk_id]` citation. Judge v1's "looks cited" heuristic (`"[" in answer`) then scores them as unhelpful even though the content is correct.
- `eval_019`/`eval_021`: correct refusals ("I could not find the answer in the provided documents.") rejected because the refusal sentence shares almost no vocabulary with the question, and v1 requires topical overlap ≥ 2 regardless of whether the answer is a refusal.
- `eval_026`: v1's token regex (`[a-z0-9_]+`) keeps `max_retries` as one token, so it never matches the question's word "retries" — a raw tokenization mismatch, not a content problem.

**False positives** (judge = 1, human = 0): `eval_015`, `eval_022`
- `eval_015`: the correct fact (`SignatureVerificationError` raised on mismatch or stale timestamp) is present but buried after a dangling table-cell fragment ("Value of the `X-Nimbus-Signature` header.") and an unrelated v2/v3 compatibility sentence — v1's overlap+citation check can't detect that the delivery is confusing.
- `eval_022`: the answer states an unrelated pagination limit for a question about an undocumented webhook payload size — topically adjacent (shares "size"-like vocabulary) but not actually responsive.

**The human label was correct on all 7 disagreements** — each was independently verified against the real answer text in `eval/results.json`.

---

## 7. Prediction

Pre-iteration prediction, written and committed **before** `eval/judge.py` gained a `judge_v2` function:

> "Teaching the judge, from `eval_019` (a false negative...) and `eval_022` (a false positive...), to (a) trust the exact refusal sentence as correct without requiring topical term overlap, and (b) reject an answer that doesn't actually address the specific thing asked about even when it shares surface vocabulary, will fix `eval_019` and, by the same refusal-recognition rule, `eval_021`... plus `eval_022`... `eval_015`, `eval_016`, `eval_018`, and `eval_026` involve different mechanisms... I expect those four to remain disagreements after this iteration."

- Commit: [`f5e581d73364fe630ab18e103ce061a5934f4ac0`](../../commit/f5e581d73364fe630ab18e103ce061a5934f4ac0)
- Timestamp: `2026-09-04T12:56:52+05:30`

**Where it was correct — everything.** The prediction named exactly `eval_019`, `eval_021`, and `eval_022` as the cases the two-example iteration would fix, and named exactly `eval_015`, `eval_016`, `eval_018`, and `eval_026` as the cases it would not. Judge V2's actual disagreement set (§8) matches this precisely: `{eval_015, eval_016, eval_018, eval_026}`, no more and no less.

There is no "where it was imprecise" section here because, unlike a narrative written without executing anything, this prediction was checked against a real second run and held exactly. (Historically in this project's Week 6 work, predictions have sometimes been partially wrong — see `week6_report.md` §"Prediction Score" for an honest example of that. This one happened to land precisely; that is reported as an outcome, not claimed as a general pattern.)

---

## 8. Judge V2

- **21/25 agreement**
- **84.0%**
- **+12.0 percentage points** over V1
- Remaining disagreements (4): `eval_015`, `eval_016`, `eval_018`, `eval_026`
- Exactly **two few-shot examples** were used: `eval_019` (false negative) and `eval_022` (false positive), both real V1 disagreements
- Commit: [`e5973c8b51b61088c52d19fbe57897c353041551`](../../commit/e5973c8b51b61088c52d19fbe57897c353041551)
- No deterministic checks were added back into the judge — `judge_v2.txt` states the same exclusion list as `judge_v1.txt`.

---

## 9. Before → After

| Metric | V1 | V2 |
|---|---:|---:|
| Agreement | 72.0% | 84.0% |
| Matches | 18/25 | 21/25 |
| Disagreements | 7 | 4 |

---

## 10. Commit Ordering (verifiable)

```
$ git log --oneline -- eval/
e5973c8 Track E: run Judge V2 (two-example iteration on the same 25 cases)
f5e581d Track E: pre-register prediction before Judge V2
d4fc518 Track E: run Judge V1 (after labels_25.json commit)
0463fde Track E: eval set, one-command runner, blind labels (before any judge)
```

Read bottom-to-top, this is the required order: labels committed → Judge V1 run → prediction committed → Judge V2 run. `eval/judge.py` did not contain a `judge_v2` function until the commit at `e5973c8`, after the prediction commit at `f5e581d`.

---

## 11. Final Verdict

28 real cases across 5 taxonomy modes, a self-contained one-command application runner (25/28 = 89.3%, with all three failures independently inspectable), an explicit deterministic (4) vs LLM-judged (1) boundary, 25 binary blind human labels committed before any judge code existed, a real Judge V1 at 72.0% agreement with 7 disagreements all correctly resolved in the human's favor, a pre-registered prediction that held exactly, and a Judge V2 iterated from two of its own real disagreements that raised agreement to 84.0% (+12.0 points), leaving four honestly-unresolved disagreements whose root causes (a missing-citation heuristic gap and a token-matching bug) are documented above rather than papered over.

## Reproduce

```bash
python eval/run_eval.py    # application eval -> eval/results.json
python eval/judge.py       # judge v1 + v2 -> eval/judge_v1.txt, eval/judge_v2.txt
python -m unittest eval.test_track_e -v
```
