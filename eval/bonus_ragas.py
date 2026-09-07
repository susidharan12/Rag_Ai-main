"""Track E bonus - RAGAS-style faithfulness + context precision.

    python eval/bonus_ragas.py

The real `ragas` package scores faithfulness by asking an LLM to decompose
an answer into claims and verify each against the retrieved context - that
needs a working LLM judge, and this environment has no GROQ_API_KEY
configured (generate_groq fails over to the deterministic extractive
generator - see rag_core/pipeline.py). So this is a deterministic, no-LLM
PROXY for the same two RAGAS ideas, clearly labeled as such rather than
presented as the real library's output:

  faithfulness_proxy(answer, context)
      Word-overlap fraction of the answer's content words that also appear
      in the exact chunk(s) it was generated from. The extractive-v2
      generator only ever quotes/extracts retrieved text (never
      paraphrases), so this proxy is a legitimate stand-in for "is every
      claim grounded in the retrieved context": for this generator it is
      trivially close to 1.0 - which is itself the point of this bonus
      (see below).

  context_version_precision(answer, question, cited_chunk)
      1 if the SDK version actually backing the answer matches the version
      the question resolves to (rag_core.store._resolve_version_preference
      - v3 by default for a versionless question); 0 otherwise. Unlike
      faithfulness, this checks whether the retrieved context was the
      *right* context, not just whether the answer is loyal to it.

The bonus asks for one answer that is faithful (>=0.9) yet grounded in the
wrong SDK version for the question asked - "confidently, faithfully
wrong" - and an explanation of why an averaged faithfulness score alone
would hide it. Section 2 below is that case, reconstructed from this
project's own real Week 5 bug (documented in week5_error_analysis/ and in
server/main.py's benchmark payload as failure case F1: "Without an
sdk_version filter, a v2 chunk outranks the v3 row and presents the
outdated default") and from the *current* generator code, run for real.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

EVAL_INDEX_DIR = os.path.join(HERE, ".eval_index")
os.environ.setdefault("RAG_DATA_DIR", EVAL_INDEX_DIR)

from rag_core import settings  # noqa: E402
from rag_core.generators import generate_extractive  # noqa: E402
from rag_core.pipeline import ask_sync  # noqa: E402
from rag_core.store import DocStore, _resolve_version_preference  # noqa: E402

CASES_PATH = os.path.join(HERE, "eval_cases.json")
RESULTS_PATH = os.path.join(HERE, "results.json")
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "in", "on", "for",
    "to", "and", "or", "what", "which", "who", "how", "does", "do",
    "sdk", "by", "with",
}


def _content_words(text):
    # A bare digit ("5", "10") is often exactly the fact being checked for
    # groundedness, so only the len>1 filter applies to alphabetic tokens.
    return {w for w in re.findall(r"[a-z0-9_]+", text.lower())
            if w not in STOPWORDS and (w.isdigit() or len(w) > 1)}


def faithfulness_proxy(answer, context_text):
    """Fraction of the answer's content words attested in context_text."""
    ans_words = _content_words(answer)
    if not ans_words:
        return None
    ctx_words = _content_words(context_text)
    supported = ans_words & ctx_words
    return round(len(supported) / len(ans_words), 3)


def _chunk_text(store, chunk_id):
    store.ensure_loaded()
    for text, meta in zip(store._state["chunks"], store._state["metadata"]):
        if meta["chunk_id"] == chunk_id:
            return text, meta
    return None, None


def section_1_corpus_wide_faithfulness(store):
    """Faithfulness proxy over every docs-backed (expect="answer") case in
    the 28-case eval set, using each case's own cited context chunks - the
    "average faithfulness" the bonus says can hide a real regression."""
    cases = json.loads(open(CASES_PATH, encoding="utf-8").read())["cases"]
    results = json.loads(open(RESULTS_PATH, encoding="utf-8").read())["results"] \
        if os.path.exists(RESULTS_PATH) else None
    if results is None:
        print("Run `python eval/run_eval.py` first - eval/results.json not found.")
        return []

    by_id = {r["id"]: r for r in results}
    rows = []
    for case in cases:
        if case["expect"] != "answer":
            continue
        r = by_id.get(case["id"])
        if not r or r["refused"]:
            continue
        payload, trace = ask_sync(case["question"], generator="extractive", store=store, surface="eval")
        context_ids = trace["generation"]["context_chunk_ids"]
        context_text = "\n".join(
            trace["retrieval"]["retrieved_texts"].get(cid, "")
            for cid in context_ids
        )
        # retrieved_texts only covers the top_k retrieval window; for the
        # over-fetched extractive context, fall back to the store directly.
        if not context_text.strip():
            texts = []
            for cid in context_ids:
                t, _m = _chunk_text(store, cid)
                if t:
                    texts.append(t)
            context_text = "\n".join(texts)
        score = faithfulness_proxy(payload["answer"], context_text)
        rows.append({"id": case["id"], "mode": case["mode"], "faithfulness": score})
    return rows


def section_2_confidently_wrong_version(store):
    """The bonus's specific ask: one answer >=0.9 faithfulness, wrong SDK
    version for the question. Demonstrated on eval_027's real question
    ("What is the default pool_size for Client.connect()?" - versionless,
    resolves to v3) using the ACTUAL v2 corpus chunk and the CURRENT
    generate_extractive code, run for real - not fabricated text.

    The chosen chunk (v2 client_connect.md's "## Parameters" table) is the
    worst case on purpose: it is a real chunk in this corpus whose OWN text
    never says "v2" or "v3" anywhere - just a bare markdown table row
    ("pool_size | int | 5 | ..."). If retrieval ever surfaces only this
    chunk (a genuine retrieval-failure shape: the v2 and v3 pages are near-
    tied on raw similarity for this question - see below - and this is
    exactly the historical bug documented as failure case F1 in
    server/main.py's benchmark payload / week5_error_analysis), the only
    thing standing between a correct v3=10 answer and a silently wrong
    v2=5 answer is the generator explicitly stating which version a
    parameter-table number came from.
    """
    question = "What is the default pool_size for Client.connect()?"
    pref = _resolve_version_preference(question)

    v2_intro_id = "c-users-akash-t-rag-ai-main-nimbus-sdk-v2-client-connect-2c9eb3:p1:c0"
    v3_intro_id = "c-users-akash-t-rag-ai-main-nimbus-sdk-v3-client-connect-27c00a:p1:c0"
    v2_table_id = "c-users-akash-t-rag-ai-main-nimbus-sdk-v2-client-connect-2c9eb3:p2:c0"
    v2_text, v2_meta = _chunk_text(store, v2_table_id)
    if not v2_text:
        print("Expected v2 client_connect param-table chunk id not found in "
              "the eval index - run `python eval/run_eval.py` once first to "
              "build it.")
        return None

    # 1) Evidence this isn't hypothetical: on raw embedding similarity alone
    #    (no version-preference/lexical boost - the two things that make the
    #    live app choose correctly), the v2 and v3 "intro" chunks for this
    #    exact versionless question are a near-tie, with v2 fractionally
    #    AHEAD - the same shape as the historical bug documented as failure
    #    case F1 in server/main.py's benchmark payload. Retrieval genuinely
    #    can put v2 content ahead of v3 for this question; nothing about
    #    that risk is invented for this demo.
    raw_scores = {}
    for r in store.search(question, top_k=10):
        if r["chunk_id"] in (v2_intro_id, v3_intro_id):
            raw_scores[r["chunk_id"]] = r["score"]

    # The v2 PARAMETER TABLE chunk (which actually carries the pool_size=5
    # fact) ranks lower under the live app's current, already-fixed ranking -
    # reported here for transparency about what's observed vs. what's
    # deliberately constructed below to isolate the GENERATION-layer risk
    # (what _find_parameter does once a v2 chunk is in its input) from the
    # RETRIEVAL-layer risk (point 1, above).
    table_chunk_live_rank = next(
        (r["rank"] for r in store.search(question, top_k=10)
         if r["chunk_id"] == v2_table_id), None)

    # 2) Counterfactual retrieval: what if ONLY this v2 table chunk had
    #    been surfaced? Feed the REAL v2 chunk to the REAL current
    #    generator - nothing about the answer text below is written by
    #    hand.
    v2_only_result = [{
        "chunk_id": v2_table_id, "source_doc": v2_meta["source_file"],
        "doc_id": v2_meta["doc_id"], "text": v2_text, "score": 0.66,
        "rank": 1, "page_number": v2_meta.get("page_number", 1),
        "sdk_version": v2_meta.get("sdk_version", ""),
        "lexical_overlap": 0.3, "heading_overlap": 0.3,
    }]
    out = generate_extractive(question, v2_only_result, store=store)
    answer = out["answer"]

    faithfulness = faithfulness_proxy(answer, v2_text)
    chunk_text_states_version = bool(re.search(r"\bv[23]\b", v2_text.lower()))
    version_in_answer = "v2" if re.search(r"\bv2\b", answer.lower()) else (
        "v3" if re.search(r"\bv3\b", answer.lower()) else None)
    context_version_precision = 1 if version_in_answer == pref else 0

    # Counterfactual: this exact bonus exercise is what surfaced that
    # _find_parameter() didn't state which SDK version a parameter default
    # came from - fixed earlier in this same session (rag_core/generators.py,
    # _find_parameter). Reconstruct the pre-fix wording (strip the "In SDK
    # vX, " prefix this fix adds) to show the version this bonus is actually
    # asking to find: >=0.9 faithful, and completely silent on version.
    prefix_match = re.match(r"^(In SDK v[23], )", answer)
    prefix_answer = answer[prefix_match.end():] if prefix_match else answer
    prefix_faithfulness = faithfulness_proxy(prefix_answer, v2_text)

    return {
        "question": question,
        "question_resolves_to": pref,
        "raw_cosine_similarity_v2_vs_v3_intro_chunks": raw_scores,
        "v2_param_table_chunk_live_retrieval_rank": table_chunk_live_rank,
        "source_chunk_states_a_version_itself": chunk_text_states_version,
        "answer": answer,
        "faithfulness_proxy": faithfulness,
        "version_stated_in_answer": version_in_answer,
        "context_version_precision": context_version_precision,
        "pre_fix_reconstruction": {
            "note": "_find_parameter() before this session's version-prefix "
                    "fix (rag_core/generators.py) returned exactly this, with "
                    "no version prefix:",
            "answer": prefix_answer,
            "faithfulness_proxy": prefix_faithfulness,
            "context_version_precision": 0,
        },
    }


def main():
    store = DocStore()
    store.ensure_loaded()
    if store.stats()["documents"] == 0:
        print("eval/.eval_index is empty - run `python eval/run_eval.py` once "
              "first to build it.")
        return

    print("Track E bonus - RAGAS-style faithfulness + context precision")
    print("(deterministic proxy, not the `ragas` package - see module docstring)\n")

    print("=== 1. Corpus-wide faithfulness (25/28 answered, non-refused cases) ===")
    rows = section_1_corpus_wide_faithfulness(store)
    scored = [r["faithfulness"] for r in rows if r["faithfulness"] is not None]
    avg = round(sum(scored) / len(scored), 3) if scored else None
    for r in rows:
        print(f"  {r['id']}\t{r['mode']}\tfaithfulness={r['faithfulness']}")
    print(f"\n  average faithfulness across {len(scored)} cases: {avg}")

    print("\n=== 2. Confidently, faithfully wrong (the bonus's specific ask) ===")
    demo = section_2_confidently_wrong_version(store)
    if demo:
        print(f"  question: {demo['question']!r}")
        print(f"  this question resolves to: {demo['question_resolves_to']} "
              f"(rag_core.store._resolve_version_preference)")
        print(f"  raw cosine similarity, v2 vs v3 intro chunks (no version/lexical "
              f"boost): {demo['raw_cosine_similarity_v2_vs_v3_intro_chunks']} "
              f"(near-tied - same shape as historical failure case F1)")
        print(f"  v2 param-table chunk's own live retrieval rank for this question: "
              f"{demo['v2_param_table_chunk_live_retrieval_rank']} "
              f"(fed to the generator directly below to isolate the generation-layer risk)")
        print(f"  source chunk itself states a version (v2/v3)? "
              f"{demo['source_chunk_states_a_version_itself']} (a bare param table row)")
        print(f"  answer actually produced: {demo['answer']!r}")
        print(f"  faithfulness_proxy: {demo['faithfulness_proxy']}  "
              f"(>= 0.9 => the bonus's threshold)")
        print(f"  version stated in answer: {demo['version_stated_in_answer']}")
        print(f"  context_version_precision: {demo['context_version_precision']} "
              f"(1 = right version, 0 = wrong version for the question asked)")
        pre = demo["pre_fix_reconstruction"]
        print(f"\n  {pre['note']}")
        print(f"    answer: {pre['answer']!r}")
        print(f"    faithfulness_proxy: {pre['faithfulness_proxy']}  "
              f"(>= 0.9 => THIS is the bonus's exact case: faithful, wrong version, "
              f"and nothing in the text itself says so)")
        print(f"    context_version_precision: {pre['context_version_precision']}")
        print()
        if avg is not None and pre["faithfulness_proxy"] is not None:
            print(f"  Why the average hides it: corpus-wide average faithfulness "
                  f"is {avg} - indistinguishable from this case's "
                  f"{pre['faithfulness_proxy']}. Faithfulness alone cannot "
                  f"tell a v3-correct answer from a v2-wrong one; only "
                  f"context_version_precision (or the api_version_stated "
                  f"deterministic assertion in eval/run_eval.py) can.")

    out_path = os.path.join(HERE, "bonus_ragas_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "corpus_wide_faithfulness": rows,
            "average_faithfulness": avg,
            "confidently_wrong_demo": demo,
        }, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
