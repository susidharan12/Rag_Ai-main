"""Regression tests for golden_set.jsonl (the Week 3/4 CLI eval pipeline).

Companion to week6_error_analysis/test_week6_eval.py, which covers the
Week 6 judge eval (labels_25.json). This file covers the other test-case
set in the repo: the iOS/Android golden set scored by sdk_eval_week4.py
against vectors.index/chunks.pkl (built by pdf_reader.py).

Structural checks (ids, required fields, known_chunk content) always run.
The retrieval checks additionally require a built index - run

    python pdf_reader.py documents/iOS_Development_Documentation.pdf documents/Android_Development_Documentation.pdf

first if vectors.index/chunks.pkl are missing (they are gitignored,
generated artifacts, same as chunks.pkl for the live app's data/index/).
"""

import json
import os
import pickle
import unittest

import faiss
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_SET_PATH = os.path.join(HERE, "golden_set.jsonl")
INDEX_PATH = os.path.join(HERE, "vectors.index")
CHUNKS_PATH = os.path.join(HERE, "chunks.pkl")

REQUIRED_FIELDS = ("id", "question", "known_chunk", "known_page",
                    "known_answer", "exact_tokens")


def load_cases():
    with open(GOLDEN_SET_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def index_built():
    return os.path.exists(INDEX_PATH) and os.path.exists(CHUNKS_PATH)


class GoldenSetStructureTests(unittest.TestCase):
    """These run unconditionally - no built index required."""

    def setUp(self):
        self.cases = load_cases()

    def test_file_has_at_least_a_dozen_cases(self):
        self.assertGreaterEqual(len(self.cases), 12)

    def test_ids_are_unique(self):
        ids = [c["id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_case_has_required_fields(self):
        for case in self.cases:
            for field in REQUIRED_FIELDS:
                self.assertIn(field, case, f"{case.get('id')} missing '{field}'")

    def test_known_chunk_is_a_non_negative_int(self):
        for case in self.cases:
            self.assertIsInstance(case["known_chunk"], int, case["id"])
            self.assertGreaterEqual(case["known_chunk"], 0, case["id"])

    def test_exact_tokens_is_a_non_empty_list(self):
        for case in self.cases:
            self.assertIsInstance(case["exact_tokens"], list, case["id"])
            self.assertGreater(len(case["exact_tokens"]), 0, case["id"])

    def test_questions_are_non_trivial(self):
        for case in self.cases:
            self.assertGreater(len(case["question"].strip()), 10, case["id"])


@unittest.skipUnless(
    index_built(),
    "vectors.index/chunks.pkl not built - run "
    "'python pdf_reader.py documents/iOS_Development_Documentation.pdf "
    "documents/Android_Development_Documentation.pdf' first",
)
class GoldenSetIndexContentTests(unittest.TestCase):
    """Every known_chunk must genuinely contain its exact_tokens - this is
    the check that would have caught the duplicated-PDF-pages bug (see
    week6_task_e_report.md-style analysis): a wrong or stale chunk index
    silently makes the golden set unverifiable."""

    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases()
        with open(CHUNKS_PATH, "rb") as f:
            data = pickle.load(f)
        cls.chunks = data["chunks"]
        cls.metadata = data["metadata"]

    def test_known_chunk_in_range(self):
        for case in self.cases:
            self.assertLess(case["known_chunk"], len(self.chunks),
                             f"{case['id']}: known_chunk out of range for a "
                             f"{len(self.chunks)}-chunk index")

    def test_known_chunk_contains_every_exact_token(self):
        for case in self.cases:
            text = self.chunks[case["known_chunk"]].lower()
            for token in case["exact_tokens"]:
                self.assertIn(token.lower(), text,
                               f"{case['id']}: known_chunk {case['known_chunk']} "
                               f"does not contain exact_token {token!r}")

    def test_source_doc_matches_indexed_metadata(self):
        for case in self.cases:
            source_doc = case.get("source_doc")
            if not source_doc:
                continue
            meta = self.metadata[case["known_chunk"]]
            self.assertEqual(meta.get("source_file"), source_doc, case["id"])


@unittest.skipUnless(
    index_built(),
    "vectors.index/chunks.pkl not built - see GoldenSetIndexContentTests",
)
class GoldenSetRetrievalSmokeTest(unittest.TestCase):
    """A loose smoke test, not a strict regression pin: dense hit@3 should
    stay comfortably above chance. Guards against a catastrophic corpus
    regression (e.g. the duplicated-PDF-pages issue that once dropped this
    to a noisy ~0.35) without being brittle to small ranking wobbles."""

    MIN_HIT_AT_3 = 0.5

    def test_dense_hit_at_3_above_floor(self):
        from pdf_reader import get_embedding_model

        cases = load_cases()
        index = faiss.read_index(INDEX_PATH)
        model = get_embedding_model()

        hits = 0
        for case in cases:
            vec = np.array(model.encode([case["question"]], convert_to_numpy=True),
                            dtype="float32")
            faiss.normalize_L2(vec)
            _, ids = index.search(vec, 3)
            if case["known_chunk"] in ids[0]:
                hits += 1

        rate = hits / len(cases)
        self.assertGreaterEqual(
            rate, self.MIN_HIT_AT_3,
            f"dense hit@3 = {hits}/{len(cases)} = {rate:.2f}, "
            f"below the {self.MIN_HIT_AT_3} floor")


if __name__ == "__main__":
    unittest.main(verbosity=2)
