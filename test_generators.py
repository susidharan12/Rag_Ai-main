"""Regression tests for rag_core/generators.py's extractive-v2 fallback.

Covers the "tell me about X" bug: a broad/summary question shares almost
no literal vocabulary with detailed source text even when retrieval is
genuinely on-topic, so the lexical-overlap relevance gate (correctly
protecting against real out-of-corpus questions) would otherwise refuse
a perfectly answerable question. See week5_error_analysis/traces/traces.jsonl
trace tr_20260904_082821_01f9dc for the real, reported case this fixes.

Uses synthetic result dicts (no embeddings/network needed) so this runs
fast and deterministically.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag_core.generators import (  # noqa: E402
    _broad_overview_answer,
    _dominant_source_doc,
    generate_extractive,
)


def _chunk(source_doc, text, score=0.18, chunk_id=None, lexical_overlap=0.0, heading_overlap=0.0):
    return {
        "chunk_id": chunk_id or f"{source_doc}:c0",
        "source_doc": source_doc,
        "text": text,
        "score": score,
        "rank": 1,
        "lexical_overlap": lexical_overlap,
        "heading_overlap": heading_overlap,
        "sdk_version": "",
    }


RESUME_TEXT = (
    "Senior CMS Developer\n\nProject Name: Socrat.AI\nTechnologies: WordPress, PHP, MySQL.\n"
    "Description: Socrat.ai is an AI-powered educational platform."
)


class DominantSourceDocTests(unittest.TestCase):
    def test_single_document_dominates(self):
        results = [_chunk("resume.pdf", RESUME_TEXT, chunk_id=f"resume.pdf:c{i}") for i in range(5)]
        self.assertEqual(_dominant_source_doc(results), "resume.pdf")

    def test_scattered_documents_have_no_dominant_doc(self):
        results = [
            _chunk("a.pdf", "text a"), _chunk("b.pdf", "text b"),
            _chunk("c.pdf", "text c"), _chunk("d.pdf", "text d"),
            _chunk("e.pdf", "text e"),
        ]
        self.assertIsNone(_dominant_source_doc(results))

    def test_empty_results(self):
        self.assertIsNone(_dominant_source_doc([]))


class BroadOverviewAnswerTests(unittest.TestCase):
    def test_returns_none_for_non_broad_question(self):
        results = [_chunk("resume.pdf", RESUME_TEXT, chunk_id=f"resume.pdf:c{i}") for i in range(5)]
        self.assertIsNone(_broad_overview_answer("What is the pool_size default?", results))

    def test_returns_none_when_no_dominant_document(self):
        results = [
            _chunk("a.pdf", "text a"), _chunk("b.pdf", "text b"),
            _chunk("c.pdf", "text c"), _chunk("d.pdf", "text d"),
            _chunk("e.pdf", "text e"),
        ]
        self.assertIsNone(_broad_overview_answer("Tell me about the candidate", results))

    def test_returns_none_below_score_floor(self):
        results = [_chunk("resume.pdf", RESUME_TEXT, score=0.05, chunk_id=f"resume.pdf:c{i}")
                   for i in range(5)]
        self.assertIsNone(_broad_overview_answer("Tell me about the candidate", results))

    def test_answers_broad_question_with_dominant_relevant_document(self):
        results = [_chunk("resume.pdf", RESUME_TEXT, chunk_id=f"resume.pdf:c{i}") for i in range(5)]
        result = _broad_overview_answer("tell me about the candidate", results)
        self.assertIsNotNone(result)
        overview, chunk = result
        self.assertIn("Senior CMS Developer", overview)
        self.assertEqual(chunk["source_doc"], "resume.pdf")

    def test_matches_several_broad_intent_phrasings(self):
        results = [_chunk("resume.pdf", RESUME_TEXT, chunk_id=f"resume.pdf:c{i}") for i in range(5)]
        for question in (
            "Tell me about the candidate",
            "Summarize this document",
            "Give me an overview of this",
            "Who is this candidate",
        ):
            with self.subTest(question=question):
                self.assertIsNotNone(_broad_overview_answer(question, results))


class GenerateExtractiveBroadQuestionTests(unittest.TestCase):
    """End-to-end through generate_extractive(), matching the real trace."""

    def test_real_reported_case_now_answers_instead_of_refusing(self):
        results = [
            _chunk("resume.pdf", RESUME_TEXT, score=0.1876, chunk_id="resume.pdf:p4:c0"),
            _chunk("resume.pdf", "Project Name: Thinkarguments. WordPress, PHP.",
                   score=0.1725, chunk_id="resume.pdf:p3:c0"),
            _chunk("resume.pdf", "Team Size: 25. JIRA.", score=0.1654, chunk_id="resume.pdf:p3:c1"),
            _chunk("resume.pdf", "Project Name: ICAR-IIHR. Drupal 11.",
                   score=0.1578, chunk_id="resume.pdf:p5:c0"),
            _chunk("resume.pdf", "Project Name: Selvie. WordPress.",
                   score=0.1471, chunk_id="resume.pdf:p6:c0"),
        ]
        out = generate_extractive("tell me about the candidate", results)
        self.assertFalse(out["refused"])
        self.assertIn("Senior CMS Developer", out["answer"])
        self.assertEqual(out["params"].get("strategy"), "broad_overview")

    def test_genuinely_out_of_corpus_broad_question_still_refuses(self):
        """Scattered, low-relevance results (the realistic shape of an
        out-of-corpus query) must not be answered just because the wording
        looks broad."""
        results = [
            _chunk("sdk.md", "Client.send() retries with backoff.", score=0.09, chunk_id="sdk.md:c0"),
            _chunk("sports.pdf", "Football has 11 players per side.", score=0.08, chunk_id="sports.pdf:c0"),
            _chunk("android.pdf", "Kotlin is Google's recommended language.", score=0.07, chunk_id="android.pdf:c0"),
        ]
        out = generate_extractive("Tell me about quantum computing", results)
        self.assertTrue(out["refused"])
        self.assertEqual(out["params"].get("reason"), "no_question_overlap")


if __name__ == "__main__":
    unittest.main(verbosity=2)
