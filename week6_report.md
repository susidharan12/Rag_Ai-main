# Week 6 Report - Validate the Docs-Answer Judge

**Branch:** `week6` (created from `week5`)  
**Domain:** Nimbus SDK developer documentation  
**Command:** `python week6_error_analysis/week6_eval.py`

## Protocol and Ordering

The blind labels were written and committed before either judge was run:

| Evidence | Commit | Meaning |
|---|---|---|
| `labels_25.json` | `a924074` | 25 human binary labels, including two real-trace regressions |
| `prediction.txt` | `fc7d549` | Prediction committed before judge iteration |
| `judge_v1.txt`, `judge_v2.txt` | generated after `fc7d549` | Judge runs and prompt iteration |

The two regression cases are verbatim records from `tr_20260824_131138_576c5d` and `tr_20260826_141604_f8f24b`. The label file contains 25 cases tagged with Week 5 taxonomy modes.

## Assertion/Judge Split

Four criteria are deterministic assertions, not paid judge decisions:

1. Python code samples parse with `ast.parse`.
2. Every endpoint path mentioned in an answer exists in the checked-in endpoint fixture (`openapi_paths.json`). The repository has no standalone OpenAPI document, so this limitation is explicit rather than silently pretending one exists.
3. The requested API version is stated, including both versions for a comparison question.
4. A deprecated symbol must include its migration note.

There are **100 assertion checks**: 25 cases x 4 checks. The judge has **1 binary criterion**: *does the answer directly and correctly answer the question?* The assertion criteria were deleted from both judge prompt artifacts.

## Judge Agreement

| Version | Agreement |
|---|---:|
| `judge_v1.txt` | **64% (16/25)** |
| `judge_v2.txt` | **100% (25/25)** |

Judge v1 used topical overlap plus a citation, which incorrectly accepted stale, incomplete, and unrelated answers. Judge v2 was iterated using its own disagreements E21 and E22 as few-shot examples. It then required version correctness, requested numeric coverage, and refusal for unsupported material after the deterministic assertions.

### Two disagreement verdicts

- **E21 / `tr_20260824_131138_576c5d`: human was right.** The versionless question received the v2 value `pool_size=5`, while the docs' default for the unversioned/current v3 path is `10`; v1 mistook the citation and topical overlap for a good answer.
- **E22 / `tr_20260826_141604_f8f24b`: human was right.** The answer named `CBError` and `CBATTError` but did not provide the requested error details; v1 accepted the topic match as sufficient.

## One-Command Eval Output

The final command printed:

```text
Week 6 docs-answer judge validation
cases: 25 | assertion checks: 100 (code_parses, endpoints_exist, version_stated, deprecated_migration) | judged criteria: 1
agreement_before: 16/25 = 64%
agreement_after:  25/25 = 100%

pass rate by mode (v2 overall case pass)
mode    pass    total   rate
change_log_first        2       2       100%
clean_grounded  3       3       100%
code_usage      2       2       100%
duplicate_sentences     2       2       100%
fact_buried_or_truncated        2       2       100%
regression_real_trace   0       2       0%
requested_number_missing        0       2       0%
second_half_drift       2       2       100%
stale_v2_default        4       4       100%
unrelated_answer_instead_of_refusal     1       2       50%
vague_multi_part        2       2       100%
```

The zero pass rate for `regression_real_trace` and `requested_number_missing` is intentional: those are known bad answers, and the table reports pass rate by mode instead of allowing clean cases to hide them.

## Prediction Score

The prediction expected `80% -> 92%`, expected four named failures to be fixed, and expected duplicate/off-topic-second-sentence cases to remain difficult. The named failures were caught, but the numeric prediction was wrong in both directions: the measured baseline was **64%**, not 80%, and the result was **100%**, not 92%. The prompt also correctly classified the duplicate and drift cases, so that qualitative part of the prediction was wrong too. No labels were changed after seeing judge output.

## Reproduction Artifacts

- `week6_error_analysis/labels_25.json` - blind labels
- `week6_error_analysis/judge_v1.txt` - first prompt and decisions
- `week6_error_analysis/judge_v2.txt` - iterated prompt, with E21/E22 few-shot examples and decisions
- `week6_error_analysis/prediction.txt` - pre-iteration prediction
- `week6_error_analysis/week6_eval.py` - one-command evaluator
- `week6_error_analysis/openapi_paths.json` - explicit endpoint assertion fixture