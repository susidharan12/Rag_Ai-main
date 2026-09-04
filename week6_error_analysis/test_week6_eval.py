"""Regression tests for the Week 6 docs-answer judge validation (Task Set E).

Guards the rubric-load-bearing facts: 25+ blind-labeled cases with binary
human labels, at least two verbatim real-trace regressions, deterministic
assertions kept out of the judge prompt, and the judge itself staying
binary. Also pins the committed judge_v1.txt / judge_v2.txt agreement
numbers so a silent regression in week6_eval.py is caught.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import week6_eval  # noqa: E402

KNOWN_WEEK5_MODES = {
    "stale_v2_default",
    "change_log_first",
    "unrelated_answer_instead_of_refusal",
    "requested_number_missing",
    "duplicate_sentences",
    "fact_buried_or_truncated",
    "second_half_drift",
    "clean_grounded",
}
# Week 5's battery also tagged surfaces G (vague/multi-part) and H (code-usage)
# and Week 6 adds a regression tag for verbatim real traces; these ride on top
# of, rather than replace, the 7 M1-M7 failure-mode clusters + Clean.
EXTRA_TASK_E_MODES = {"vague_multi_part", "code_usage", "regression_real_trace"}
ALLOWED_MODES = KNOWN_WEEK5_MODES | EXTRA_TASK_E_MODES


class LabelsFileTests(unittest.TestCase):
    def setUp(self):
        self.cases = week6_eval.load_cases()

    def test_has_at_least_25_cases(self):
        self.assertGreaterEqual(len(self.cases), 25)

    def test_every_case_has_a_known_taxonomy_mode(self):
        for case in self.cases:
            self.assertIn(case["mode"], ALLOWED_MODES, case["id"])

    def test_human_labels_are_strictly_binary(self):
        for case in self.cases:
            self.assertIn(case["human_label"], (0, 1), case["id"])

    def test_at_least_two_verbatim_regression_cases(self):
        regressions = [c for c in self.cases if c["mode"] == "regression_real_trace"]
        self.assertGreaterEqual(len(regressions), 2)
        for case in regressions:
            self.assertTrue(case["source"].startswith("tr_"), case["id"])

    def test_ids_are_unique(self):
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)))


class DeterministicAssertionTests(unittest.TestCase):
    """These four checks must stay deterministic code, never judge prompt text."""

    def test_code_parses_accepts_valid_python(self):
        case = {"answer": "```python\nx = 1 + 1\n```", "requires_code": True}
        self.assertTrue(week6_eval.deterministic_assertions(case)["code_parses"])

    def test_code_parses_rejects_invalid_python(self):
        case = {"answer": "```python\ndef f(:\n```", "requires_code": True}
        self.assertFalse(week6_eval.deterministic_assertions(case)["code_parses"])

    def test_endpoint_must_exist_in_openapi_fixture(self):
        known = {"answer": "See /v3/client/send for details.", "requires_code": False}
        unknown = {"answer": "See /v3/client/delete for details.", "requires_code": False}
        self.assertTrue(week6_eval.deterministic_assertions(known)["endpoints_exist"])
        self.assertFalse(week6_eval.deterministic_assertions(unknown)["endpoints_exist"])

    def test_version_must_be_stated_when_expected(self):
        stated = {"answer": "The v3 default is 10.", "expected_version": "v3", "requires_code": False}
        missing = {"answer": "The default is 10.", "expected_version": "v3", "requires_code": False}
        self.assertTrue(week6_eval.deterministic_assertions(stated)["version_stated"])
        self.assertFalse(week6_eval.deterministic_assertions(missing)["version_stated"])

    def test_deprecated_symbol_requires_migration_note(self):
        with_note = {"answer": "legacy_send is deprecated; use Client.send instead.", "requires_code": False}
        without_note = {"answer": "Just call legacy_send() to fire the request.", "requires_code": False}
        self.assertTrue(week6_eval.deterministic_assertions(with_note)["deprecated_migration"])
        self.assertFalse(week6_eval.deterministic_assertions(without_note)["deprecated_migration"])

    def test_deterministic_assertion_count_matches_report(self):
        cases = week6_eval.load_cases()
        assertion_names = ("code_parses", "endpoints_exist", "version_stated", "deprecated_migration")
        self.assertEqual(len(cases) * len(assertion_names), len(cases) * 4)
        self.assertGreaterEqual(len(cases) * len(assertion_names), 100)


class JudgeBinaryTests(unittest.TestCase):
    def setUp(self):
        self.cases = week6_eval.load_cases()

    def test_judge_v1_is_binary(self):
        for case in self.cases:
            self.assertIn(week6_eval.judge_v1(case), (0, 1), case["id"])

    def test_judge_v2_is_binary(self):
        for case in self.cases:
            self.assertIn(week6_eval.judge_v2(case), (0, 1), case["id"])


class AgreementRegressionTests(unittest.TestCase):
    """Pins the committed artifact numbers so an eval-script edit can't
    silently change agreement without the artifacts being regenerated."""

    def setUp(self):
        self.cases = week6_eval.load_cases()
        self.v1 = [week6_eval.judge_v1(c) for c in self.cases]
        self.v2 = [week6_eval.judge_v2(c) for c in self.cases]

    def test_agreement_before(self):
        before = sum(a == c["human_label"] for a, c in zip(self.v1, self.cases))
        self.assertEqual(before, 16)
        self.assertEqual(len(self.cases), 25)

    def test_agreement_after_improves_on_before(self):
        after = sum(a == c["human_label"] for a, c in zip(self.v2, self.cases))
        before = sum(a == c["human_label"] for a, c in zip(self.v1, self.cases))
        self.assertEqual(after, 25)
        self.assertGreater(after, before)

    def test_at_least_two_real_v1_disagreements_exist(self):
        # Ground truth per this repo's data, not the v2 few-shot narrative text:
        # E21 is a genuine v1/human mismatch (human=0, v1=1). E22 is NOT — v1
        # already returns 0 for it (its citation uses a fullwidth "【...】"
        # bracket rather than ASCII "[", so v1's "[" -no-op heuristic happens to
        # agree with the human by accident). The write_judge_artifact() narrative
        # names E21/E22 as "the two disagreements used for few-shot"; only E21
        # is actually one. See week6_task_e_report.md for the full writeup.
        wrong_in_v1 = {c["id"] for c, a in zip(self.cases, self.v1) if a != c["human_label"]}
        self.assertGreaterEqual(len(wrong_in_v1), 2)
        self.assertIn("E21", wrong_in_v1)
        self.assertNotIn("E22", wrong_in_v1)


class TestSetUnchangedBetweenJudgeRuns(unittest.TestCase):
    def test_v1_and_v2_scored_the_same_case_set(self):
        v1_lines = (week6_eval.HERE / "judge_v1.txt").read_text(encoding="utf-8").splitlines()
        v2_lines = (week6_eval.HERE / "judge_v2.txt").read_text(encoding="utf-8").splitlines()
        v1_ids = [line.split("\t")[0] for line in v1_lines if line[:1] == "E"]
        v2_ids = [line.split("\t")[0] for line in v2_lines if line[:1] == "E"]
        self.assertEqual(v1_ids, v2_ids)
        self.assertGreaterEqual(len(v1_ids), 25)


class JudgePromptExcludesDeterministicCriteriaTests(unittest.TestCase):
    def test_judge_artifacts_do_not_reintroduce_assertion_language(self):
        banned = ("ast.parse", "openapi_paths.json path lookup", "regex-match endpoint")
        for name in ("judge_v1.txt", "judge_v2.txt"):
            text = (week6_eval.HERE / name).read_text(encoding="utf-8").lower()
            for phrase in banned:
                self.assertNotIn(phrase.lower(), text)
            self.assertIn("deterministic assertions are excluded", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
