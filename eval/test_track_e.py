"""Regression tests for the Track E eval (eval_cases.json / results.json /
labels_25.json / judge.py).

Structural and judge-logic checks always run. A rerun of eval/run_eval.py
against the live pipeline is deliberately NOT part of this suite (it needs
the embedding model and an index) - eval/results.json is checked as a
committed, static artifact instead, same pattern as
week6_error_analysis/test_week6_eval.py and test_golden_set.py.
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import judge as j  # noqa: E402

EVAL_CASES_PATH = os.path.join(HERE, "eval_cases.json")
RESULTS_PATH = os.path.join(HERE, "results.json")
LABELS_PATH = os.path.join(HERE, "labels_25.json")

TAXONOMY_MODES = {"factual_lookup", "conceptual_explanation",
                   "unsupported_question", "ambiguous_question",
                   "version_specific"}


def load_eval_cases():
    with open(EVAL_CASES_PATH, encoding="utf-8") as f:
        return json.load(f)


class EvalCasesTests(unittest.TestCase):
    def setUp(self):
        self.data = load_eval_cases()
        self.cases = self.data["cases"]

    def test_28_cases_total(self):
        self.assertEqual(len(self.cases), 28)

    def test_taxonomy_counts_match_declared_and_actual(self):
        declared = self.data["taxonomy_counts"]
        self.assertEqual(sum(declared.values()), 28)
        self.assertEqual(set(declared), TAXONOMY_MODES)
        actual = {}
        for c in self.cases:
            actual[c["mode"]] = actual.get(c["mode"], 0) + 1
        self.assertEqual(actual, declared)

    def test_ids_unique_and_sequential(self):
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        expected = [f"eval_{i:03d}" for i in range(1, 29)]
        self.assertEqual(sorted(ids), expected)

    def test_two_genuine_week5_regression_cases(self):
        regressions = [c for c in self.cases if c.get("source") == "week5_failure"]
        self.assertEqual(len(regressions), 2)
        for c in regressions:
            self.assertTrue(c["trace_id"].startswith("tr_"), c["id"])
        self.assertEqual({c["id"] for c in regressions}, {"eval_027", "eval_028"})

    def test_every_case_has_expect_and_question(self):
        for c in self.cases:
            self.assertIn(c["expect"], ("answer", "refuse"), c["id"])
            self.assertGreater(len(c["question"].strip()), 5, c["id"])
            if c["expect"] == "answer":
                self.assertIn("expected_tokens", c, c["id"])
                self.assertGreater(len(c["expected_tokens"]), 0, c["id"])


class ResultsArtifactTests(unittest.TestCase):
    """Checks the committed eval/results.json (last real run_eval.py run)."""

    def setUp(self):
        with open(RESULTS_PATH, encoding="utf-8") as f:
            self.results = json.load(f)

    def test_all_28_cases_present(self):
        self.assertEqual(self.results["cases"], 28)
        self.assertEqual(len(self.results["results"]), 28)

    def test_application_pass_rate_matches_by_mode_sums(self):
        total_pass = sum(m["pass"] for m in self.results["by_mode"].values())
        total_cases = sum(m["total"] for m in self.results["by_mode"].values())
        self.assertEqual(total_pass, self.results["application_pass"])
        self.assertEqual(total_cases, self.results["cases"])

    def test_every_taxonomy_mode_represented(self):
        self.assertEqual(set(self.results["by_mode"]), TAXONOMY_MODES)

    def test_deterministic_assertions_have_four_criteria(self):
        self.assertEqual(set(self.results["deterministic_assertions"]), {
            "code_sample_parses", "endpoint_exists",
            "api_version_stated", "deprecated_symbol_migration",
        })
        for name, s in self.results["deterministic_assertions"].items():
            self.assertEqual(s["applicable"] + s["na"], 28, name)
            self.assertEqual(s["passed"] + s["failed"], s["applicable"], name)

    def test_retrieval_metrics_present_and_in_range(self):
        rm = self.results["retrieval_metrics"]
        self.assertIsNotNone(rm["mrr"])
        self.assertIsNotNone(rm["rrf_mrr"])
        self.assertGreaterEqual(rm["mrr"], 0.0)
        self.assertLessEqual(rm["mrr"], 1.0)
        self.assertGreaterEqual(rm["rrf_mrr"], 0.0)
        self.assertLessEqual(rm["rrf_mrr"], 1.0)
        self.assertGreater(rm["answerable_cases"], 0)

    def test_every_result_has_a_valid_diagnosis(self):
        valid_types = {"pass", "not_in_corpus", "retrieval_failure",
                        "generation_failure", "over_answering"}
        for r in self.results["results"]:
            diag = r["diagnosis"]
            self.assertIn(diag["failure_type"], valid_types, r["id"])
            self.assertEqual(diag["failure_type"] == "pass", r["app_pass"], r["id"])

    def test_generation_failure_means_answer_was_in_context(self):
        """The specific claim this panel exists to make: a
        generation_failure case must have had a ground-truth chunk in the
        generator's actual context - otherwise it would be a retrieval
        failure, not a generation one."""
        for r in self.results["results"]:
            if r["diagnosis"]["failure_type"] == "generation_failure":
                self.assertTrue(r["diagnosis"]["context_hit"], r["id"])
                self.assertGreater(len(r["diagnosis"]["ground_truth_chunk_ids"]), 0, r["id"])

    def test_retrieval_failure_means_answer_was_not_in_context(self):
        for r in self.results["results"]:
            if r["diagnosis"]["failure_type"] == "retrieval_failure":
                self.assertFalse(r["diagnosis"]["context_hit"], r["id"])
                self.assertGreater(len(r["diagnosis"]["ground_truth_chunk_ids"]), 0, r["id"])

    def test_not_in_corpus_means_no_ground_truth_chunk_exists(self):
        for r in self.results["results"]:
            if r["diagnosis"]["failure_type"] == "not_in_corpus":
                self.assertEqual(r["diagnosis"]["ground_truth_chunk_ids"], [], r["id"])

    def test_failure_breakdown_sums_to_case_count(self):
        self.assertEqual(sum(self.results["failure_breakdown"].values()),
                          self.results["cases"])


class LabelsTests(unittest.TestCase):
    def setUp(self):
        with open(LABELS_PATH, encoding="utf-8") as f:
            self.labels = json.load(f)["labels"]
        self.case_ids = {c["id"] for c in load_eval_cases()["cases"]}

    def test_25_labels(self):
        self.assertEqual(len(self.labels), 25)

    def test_labels_are_a_subset_of_eval_cases(self):
        label_ids = {l["id"] for l in self.labels}
        self.assertTrue(label_ids.issubset(self.case_ids))

    def test_every_mode_still_represented_in_the_25(self):
        modes = {l["mode"] for l in self.labels}
        self.assertEqual(modes, TAXONOMY_MODES)

    def test_labels_are_strictly_binary(self):
        for l in self.labels:
            self.assertIn(l["human_label"], (0, 1), l["id"])

    def test_both_regression_cases_are_labeled(self):
        label_ids = {l["id"] for l in self.labels}
        self.assertIn("eval_027", label_ids)
        self.assertIn("eval_028", label_ids)


class JudgeBinaryAndDeterminismTests(unittest.TestCase):
    def setUp(self):
        self.cases = j.load_cases()

    def test_judge_v1_binary(self):
        for c in self.cases:
            self.assertIn(j.judge_v1(c), (0, 1), c["id"])

    def test_judge_v2_binary(self):
        for c in self.cases:
            self.assertIn(j.judge_v2(c), (0, 1), c["id"])

    def test_judge_v1_deterministic(self):
        for c in self.cases:
            self.assertEqual(j.judge_v1(c), j.judge_v1(c), c["id"])


class AgreementRegressionTests(unittest.TestCase):
    """Pins the real, committed agreement numbers so a code edit to
    judge.py can't silently change them without the artifacts (judge_v1.txt
    / judge_v2.txt) being regenerated and re-committed."""

    def setUp(self):
        self.cases = j.load_cases()
        self.v1 = [j.judge_v1(c) for c in self.cases]
        self.v2 = [j.judge_v2(c) for c in self.cases]

    def test_agreement_before_is_18_of_25(self):
        before = sum(a == c["human_label"] for a, c in zip(self.v1, self.cases))
        self.assertEqual(before, 18)
        self.assertEqual(len(self.cases), 25)

    def test_agreement_after_is_21_of_25(self):
        after = sum(a == c["human_label"] for a, c in zip(self.v2, self.cases))
        self.assertEqual(after, 21)

    def test_v2_improves_on_v1(self):
        before = sum(a == c["human_label"] for a, c in zip(self.v1, self.cases))
        after = sum(a == c["human_label"] for a, c in zip(self.v2, self.cases))
        self.assertGreater(after, before)

    def test_fewshot_ids_are_real_v1_disagreements(self):
        v1_wrong = {c["id"] for c, a in zip(self.cases, self.v1) if a != c["human_label"]}
        for fid in j.JUDGE_V2_FEWSHOT:
            self.assertIn(fid, v1_wrong, f"{fid} must be a genuine v1 disagreement")

    def test_predicted_remaining_disagreements(self):
        v2_wrong = {c["id"] for c, a in zip(self.cases, self.v2) if a != c["human_label"]}
        self.assertEqual(v2_wrong, {"eval_015", "eval_016", "eval_018", "eval_026"})


class TestSetUnchangedBetweenJudgeRuns(unittest.TestCase):
    def test_v1_and_v2_txt_score_the_same_case_ids(self):
        with open(os.path.join(HERE, "judge_v1.txt"), encoding="utf-8") as f:
            v1_lines = f.read().splitlines()
        with open(os.path.join(HERE, "judge_v2.txt"), encoding="utf-8") as f:
            v2_lines = f.read().splitlines()
        v1_ids = [ln.split("\t")[0] for ln in v1_lines if ln.startswith("eval_")]
        v2_ids = [ln.split("\t")[0] for ln in v2_lines if ln.startswith("eval_")]
        self.assertEqual(v1_ids, v2_ids)
        self.assertEqual(len(v1_ids), 25)


class JudgeExcludesDeterministicCriteriaTests(unittest.TestCase):
    def test_judge_artifacts_state_assertions_are_excluded(self):
        for name in ("judge_v1.txt", "judge_v2.txt"):
            with open(os.path.join(HERE, name), encoding="utf-8") as f:
                text = f.read().lower()
            self.assertIn("deterministic assertions are excluded", text)
            for criterion in ("code_sample_parses", "endpoint_exists",
                               "api_version_stated", "deprecated_symbol_migration"):
                self.assertIn(criterion, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
