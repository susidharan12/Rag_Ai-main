"""Regression tests for rag_core/generators.py's extractive-v2 fallback.

Covers two real, reported bugs on the same trace (tell me about the
candidate, week5_error_analysis/traces/traces.jsonl
tr_20260904_082821_01f9dc):

1. The lexical-overlap relevance gate refused a broad/summary question
   outright, even though retrieval was genuinely correct, because a
   broad question shares almost no literal vocabulary with detailed
   source text.
2. After fixing (1), the synthesized answer was still garbage: PDF text
   line-wraps mid-sentence and interleaves "Label: value" metadata with
   real prose, and a regex bug (\\s* around a label's colon silently
   matching newlines) caused the "Description:" section content to be
   sliced starting mid-sentence, one line late, discarding its own
   opening words. Combined with only ever using the single top chunk,
   the result was a tiny, truncated, single-project fragment instead of
   a real overview of the whole document.

Uses synthetic result dicts (no embeddings/network needed) so this runs
fast and deterministically.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag_core.generators import (  # noqa: E402
    _broad_overview_answer,
    _chunk_gist,
    _chunk_label,
    _dominant_source_doc,
    _document_opening_chunks,
    _guess_name,
    generate_extractive,
)


class _FakeStore:
    """Minimal stand-in for rag_core.store.DocStore: only what
    _document_opening_chunks() touches (ensure_loaded() + _state)."""

    def __init__(self, chunks, metadata):
        self._state = {"chunks": chunks, "metadata": metadata}

    def ensure_loaded(self):
        pass


def _chunk(source_doc, text, score=0.18, chunk_id=None, rank=1,
           lexical_overlap=0.0, heading_overlap=0.0):
    return {
        "chunk_id": chunk_id or f"{source_doc}:c0",
        "source_doc": source_doc,
        "text": text,
        "score": score,
        "rank": rank,
        "lexical_overlap": lexical_overlap,
        "heading_overlap": heading_overlap,
        "sdk_version": "",
    }


# Verbatim shape of the real resume text (PDF line-wraps and all) - this
# is what caught the \s*-swallows-newlines regex bug; a naive fixture
# without real line-wrapping wouldn't have exercised it.
SOCRAT_TEXT = (
    "Senior CMS Developer\n\n"
    "Project Name: Socrat.AI  \n"
    "Technologies: WordPress , PHP, MySQL, JQUERY, AJAX  \n"
    "Team Size: 12 \n"
    "Project Management Tool: JIRA  \n"
    "Description:  \n"
    " Socrat.ai is an AI -powered educational platform built with WordPress, focused \n"
    "on improving learning through personalized assignments and instant \n"
    "feedback.  \n"
    " The project included developing role -specific dashboards."
)

THINKARGUMENTS_TEXT = (
    "Senior CMS Developer\n\n"
    "RECENT PROFESSIONAL EXPERIENCE:\n\n"
    "Project Name: Thinkarguments  \n"
    "Technologies: WordPress , PHP, MySQL, HTML, CSS, JQUERY  \n"
    "Team Size: 25  \n"
    "Description:  \n"
    " ThinkArguments is a web -based educational platform designed to help students \n"
    "develop strong argumentation skills."
)

# A second chunk of the SAME project (Thinkarguments), the way the real
# resume splits a project's description and its responsibilities across
# two separate chunks - must be deduped by label, not answered twice.
THINKARGUMENTS_RESPONSIBILITIES_TEXT = (
    "Project Name: Thinkarguments  \n"
    "Responsibilities:  \n"
    " Built a robust backend application to support frontend functionalities."
)

# Verbatim shape of the real resume's page 1 - a running "Senior CMS
# Developer" page-header line (NOT the person's name, despite also being
# a few capitalized words) followed by the actual name on its own line,
# then contact info; this is what caught the "picked up the job title
# instead of the name" bug.
PAGE1_HEADER_TEXT = (
    "Senior CMS Developer\n\n"
    "Susidharan A  \n"
    "WordPress  | Drupal |  PHP Developer | 5+ Years  \n"
    "+91 9360689659  | susidharan @softsuave.org  \n"
    "  Senior CMS Developer"
)

PAGE1_SUMMARY_TEXT = (
    "SUMMARY :   \n"
    " 5+ years of extensive experience in Content Management System (CMS) \n"
    "development, customization, and maintenance using Drupal and WordPress.  \n"
    " Strong expertise in Drupal 8/9/10 /11, WordPress."
)


class DominantSourceDocTests(unittest.TestCase):
    def test_single_document_dominates(self):
        results = [_chunk("resume.pdf", SOCRAT_TEXT, chunk_id=f"resume.pdf:c{i}") for i in range(5)]
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


class ChunkGistAndLabelTests(unittest.TestCase):
    """Regression coverage for the \\s*-swallows-newlines bug specifically:
    the gist must start at the description's own first word, not one
    line late."""

    def test_gist_starts_at_the_descriptions_own_first_sentence(self):
        gist = _chunk_gist(SOCRAT_TEXT)
        self.assertTrue(
            gist.startswith("Socrat.ai is an AI"),
            f"gist should start with the description's own opening words, got: {gist!r}",
        )
        self.assertIn("focused on improving learning", gist)

    def test_gist_skips_bare_metadata_labels(self):
        gist = _chunk_gist(SOCRAT_TEXT)
        self.assertNotIn("Team Size", gist)
        self.assertNotEqual(gist.strip(), "Senior CMS Developer")

    def test_label_extracts_project_name(self):
        self.assertEqual(_chunk_label(SOCRAT_TEXT), "Socrat.AI")
        self.assertEqual(_chunk_label(THINKARGUMENTS_TEXT), "Thinkarguments")

    def test_label_none_when_no_label_line_present(self):
        self.assertIsNone(_chunk_label("Just some plain prose with no labels at all."))


class BroadOverviewAnswerTests(unittest.TestCase):
    def test_returns_none_for_non_broad_question(self):
        results = [_chunk("resume.pdf", SOCRAT_TEXT, chunk_id=f"resume.pdf:c{i}") for i in range(5)]
        self.assertIsNone(_broad_overview_answer("What is the pool_size default?", results))

    def test_returns_none_when_no_dominant_document(self):
        results = [
            _chunk("a.pdf", "text a"), _chunk("b.pdf", "text b"),
            _chunk("c.pdf", "text c"), _chunk("d.pdf", "text d"),
            _chunk("e.pdf", "text e"),
        ]
        self.assertIsNone(_broad_overview_answer("Tell me about the candidate", results))

    def test_returns_none_below_score_floor(self):
        results = [_chunk("resume.pdf", SOCRAT_TEXT, score=0.05, chunk_id=f"resume.pdf:c{i}")
                   for i in range(5)]
        self.assertIsNone(_broad_overview_answer("Tell me about the candidate", results))

    def test_synthesizes_across_multiple_distinct_sections(self):
        results = [
            _chunk("resume.pdf", SOCRAT_TEXT, rank=1, chunk_id="resume.pdf:p4:c0"),
            _chunk("resume.pdf", THINKARGUMENTS_TEXT, rank=2, chunk_id="resume.pdf:p3:c0"),
        ]
        result = _broad_overview_answer("tell me about the candidate", results)
        self.assertIsNotNone(result)
        overview, chunks_used = result
        self.assertIn("Socrat.AI:", overview)
        self.assertIn("Thinkarguments:", overview)
        self.assertIn("Socrat.ai is an AI", overview)
        self.assertIn("ThinkArguments is a web", overview)
        self.assertEqual(len(chunks_used), 2)
        self.assertTrue(all(c["source_doc"] == "resume.pdf" for c in chunks_used))

    def test_dedupes_a_project_that_spans_multiple_chunks(self):
        """The same project (Thinkarguments) split across two chunks -
        description in one, responsibilities in the next - must only be
        covered once, not repeated."""
        results = [
            _chunk("resume.pdf", THINKARGUMENTS_TEXT, rank=1, chunk_id="resume.pdf:p3:c0"),
            _chunk("resume.pdf", THINKARGUMENTS_RESPONSIBILITIES_TEXT, rank=2, chunk_id="resume.pdf:p3:c1"),
            _chunk("resume.pdf", SOCRAT_TEXT, rank=3, chunk_id="resume.pdf:p4:c0"),
        ]
        overview, chunks_used = _broad_overview_answer("tell me about the candidate", results)
        self.assertEqual(overview.count("Thinkarguments:"), 1)
        self.assertEqual(len(chunks_used), 2)  # Thinkarguments (once) + Socrat.AI

    def test_caps_the_number_of_parts(self):
        results = [
            _chunk("resume.pdf", f"Project Name: Project{i}  \nDescription:  \n Project {i} is a "
                                  f"real substantive description sentence about the work done.",
                   rank=i, chunk_id=f"resume.pdf:c{i}")
            for i in range(8)
        ]
        overview, chunks_used = _broad_overview_answer("tell me about the candidate", results)
        self.assertLessEqual(len(chunks_used), 5)

    def test_matches_several_broad_intent_phrasings(self):
        results = [_chunk("resume.pdf", SOCRAT_TEXT, chunk_id=f"resume.pdf:c{i}") for i in range(5)]
        for question in (
            "Tell me about the candidate",
            "Summarize this document",
            "Give me an overview of this",
            "Who is this candidate",
        ):
            with self.subTest(question=question):
                self.assertIsNotNone(_broad_overview_answer(question, results))


def _resume_store():
    """A fake store whose _state mirrors the real resume: page 1 (header
    + name, then a SUMMARY section) followed by project pages 3-6 -
    exactly what _document_opening_chunks() needs to find page 1 even
    when it isn't among the retrieved chunks."""
    chunks = [PAGE1_HEADER_TEXT, PAGE1_SUMMARY_TEXT, THINKARGUMENTS_TEXT, SOCRAT_TEXT]
    metadata = [
        {"chunk_id": "resume.pdf:p1:c0", "source_file": "resume.pdf", "doc_id": "doc1",
         "page_number": 1, "chunk_index": 0},
        {"chunk_id": "resume.pdf:p1:c1", "source_file": "resume.pdf", "doc_id": "doc1",
         "page_number": 1, "chunk_index": 1},
        {"chunk_id": "resume.pdf:p3:c0", "source_file": "resume.pdf", "doc_id": "doc1",
         "page_number": 3, "chunk_index": 0},
        {"chunk_id": "resume.pdf:p4:c0", "source_file": "resume.pdf", "doc_id": "doc1",
         "page_number": 4, "chunk_index": 0},
    ]
    return _FakeStore(chunks, metadata)


class GuessNameTests(unittest.TestCase):
    def test_finds_the_name_line_not_the_repeated_job_title(self):
        """Real reported bug: 'Senior CMS Developer' (a running page
        header, also just a few capitalized words) was being returned
        instead of the actual name 'Susidharan A' on the next line."""
        self.assertEqual(_guess_name(PAGE1_HEADER_TEXT), "Susidharan A")

    def test_skips_lines_with_digits_or_email(self):
        text = "Contact 2024\nsomeone@example.com\nReal Name Here"
        self.assertEqual(_guess_name(text), "Real Name Here")

    def test_returns_none_when_no_name_like_line_exists(self):
        self.assertIsNone(_guess_name("Project Name: X\nTechnologies: Y, Z\nTeam Size: 10"))


class DocumentOpeningChunksTests(unittest.TestCase):
    def test_returns_first_chunks_in_page_order_regardless_of_retrieval(self):
        opening = _document_opening_chunks(_resume_store(), "doc1", limit=2)
        self.assertEqual([o["chunk_id"] for o in opening],
                          ["resume.pdf:p1:c0", "resume.pdf:p1:c1"])

    def test_returns_empty_list_without_a_store(self):
        self.assertEqual(_document_opening_chunks(None, "doc1"), [])

    def test_returns_empty_list_without_a_doc_id(self):
        self.assertEqual(_document_opening_chunks(_resume_store(), None), [])


class BroadOverviewAnswerWithStoreTests(unittest.TestCase):
    """The real reported gap: retrieval surfaced only project chunks, not
    the resume's own name/summary on page 1 - the answer must still lead
    with who the document is about."""

    def test_leads_with_the_documents_own_name_and_summary(self):
        # Retrieval only found project pages (3 and 4), the realistic
        # shape of the real bug - page 1 never made the top-k for this
        # vague a query.
        results = [
            _chunk("resume.pdf", THINKARGUMENTS_TEXT, score=0.17, rank=1,
                   chunk_id="resume.pdf:p3:c0"),
            _chunk("resume.pdf", SOCRAT_TEXT, score=0.16, rank=2,
                   chunk_id="resume.pdf:p4:c0"),
        ]
        for r in results:
            r["doc_id"] = "doc1"

        overview, chunks_used = _broad_overview_answer(
            "tell me about the candidate", results, store=_resume_store())

        self.assertTrue(overview.startswith("Name: Susidharan A."))
        self.assertIn("extensive experience in Content Management System", overview)
        self.assertIn("Thinkarguments:", overview)
        self.assertIn("Socrat.AI:", overview)
        cited_ids = {c["chunk_id"] for c in chunks_used}
        self.assertIn("resume.pdf:p1:c0", cited_ids)  # the name line's chunk
        self.assertIn("resume.pdf:p1:c1", cited_ids)  # the summary chunk

    def test_works_without_a_store_falling_back_to_retrieved_chunks_only(self):
        """store is optional - callers (and the existing test suite) that
        don't pass one must keep working, just without the enrichment."""
        results = [_chunk("resume.pdf", SOCRAT_TEXT, chunk_id=f"resume.pdf:c{i}") for i in range(3)]
        result = _broad_overview_answer("tell me about the candidate", results, store=None)
        self.assertIsNotNone(result)


class GenerateExtractiveBroadQuestionTests(unittest.TestCase):
    """End-to-end through generate_extractive(), matching the real trace."""

    def test_real_reported_case_now_answers_with_a_real_overview(self):
        results = [
            _chunk("resume.pdf", SOCRAT_TEXT, score=0.1876, rank=1, chunk_id="resume.pdf:p4:c0"),
            _chunk("resume.pdf", THINKARGUMENTS_TEXT, score=0.1725, rank=2, chunk_id="resume.pdf:p3:c0"),
            _chunk("resume.pdf", THINKARGUMENTS_RESPONSIBILITIES_TEXT, score=0.1654, rank=3,
                   chunk_id="resume.pdf:p3:c1"),
        ]
        out = generate_extractive("tell me about the candidate", results)
        self.assertFalse(out["refused"])
        self.assertIn("Socrat.ai is an AI", out["answer"])
        self.assertIn("ThinkArguments is a web", out["answer"])
        self.assertEqual(out["params"].get("strategy"), "broad_overview")
        self.assertEqual(out["params"].get("sections"), 2)
        # both distinct sections must be cited
        self.assertIn("resume.pdf:p4:c0", out["answer"])
        self.assertIn("resume.pdf:p3:c0", out["answer"])

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
