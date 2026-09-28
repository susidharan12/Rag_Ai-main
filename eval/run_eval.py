"""Track E - one-command evaluator.

    python eval/run_eval.py

Ingests the Nimbus SDK corpus (corpus/nimbus_sdk/{v2,v3}/*.md + the sports
PDF - the same source set as week5_error_analysis/ingest_corpus.py) into an
isolated index under eval/.eval_index/, so this command is self-contained
and reproducible without depending on, or polluting, the live app's
data/index/. Runs every case in eval_cases.json through the deterministic
extractive-v2 generator (no LLM key required, fully replayable), applies
the 4 deterministic assertions, and writes eval/results.json.
"""

import ast
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

EVAL_INDEX_DIR = os.path.join(HERE, ".eval_index")
os.environ.setdefault("RAG_DATA_DIR", EVAL_INDEX_DIR)

from rag_core.pipeline import ask_sync  # noqa: E402
from rag_core.store import DocStore  # noqa: E402

CASES_PATH = os.path.join(HERE, "eval_cases.json")
RESULTS_PATH = os.path.join(HERE, "results.json")
OPENAPI_PATH = os.path.join(HERE, "openapi_paths.json")

REFUSAL = "i could not find the answer in the provided documents"

# No literal "deprecated" symbol exists in the corpus/nimbus_sdk docs (v2 is
# described as "in maintenance mode", not a deprecated symbol with a named
# migration target) - this map stays empty rather than inventing one, so the
# assertion honestly reports 0 applicable cases.
DEPRECATED_SYMBOLS = {}


def _ensure_index_built():
    store = DocStore()
    store.ensure_loaded()
    if store.stats()["documents"] > 0:
        return store

    import glob
    for path in sorted(glob.glob(os.path.join(REPO_ROOT, "corpus", "nimbus_sdk", "v*", "*.md"))):
        with open(path, "rb") as f:
            store.add_document(path, f.read())
    pdf = os.path.join(REPO_ROOT, "documents", "Complete_Guide_to_Major_World_Sports.pdf")
    if os.path.exists(pdf):
        with open(pdf, "rb") as f:
            store.add_document(pdf, f.read())
    return store


def _code_parses(answer):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", answer,
                         flags=re.IGNORECASE | re.DOTALL)
    if not blocks:
        return None  # not applicable
    return all(_parses(b) for b in blocks)


def _parses(source):
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


def _endpoint_exists(answer):
    mentioned = set(re.findall(r"/(?:v2|v3)/[A-Za-z0-9_/{}-]+", answer))
    if not mentioned:
        return None
    known = set(json.loads(open(OPENAPI_PATH, encoding="utf-8").read())["paths"]) \
        if os.path.exists(OPENAPI_PATH) else set()
    return mentioned <= known


def _version_stated(answer, expected_version):
    if not expected_version:
        return None
    low = answer.lower()
    if expected_version == "v2/v3":
        return "v2" in low and "v3" in low
    return expected_version in low or "maintenance" in low


def _deprecated_migration(answer):
    low = answer.lower()
    hits = [s for s in DEPRECATED_SYMBOLS if s in low]
    if not hits:
        return None
    return all(DEPRECATED_SYMBOLS[s].lower() in low for s in hits)


def deterministic_assertions(case, answer):
    return {
        "code_sample_parses": _code_parses(answer),
        "endpoint_exists": _endpoint_exists(answer),
        "api_version_stated": _version_stated(answer, case.get("expected_version")),
        "deprecated_symbol_migration": _deprecated_migration(answer),
    }


RRF_K = 60  # standard Reciprocal Rank Fusion constant
DIAGNOSTIC_DEPTH = 20  # how deep to search purely for failure diagnosis


def _ground_truth_chunk_ids(store, expected_tokens):
    """Every chunk anywhere in the corpus whose text contains every one of
    expected_tokens (case-insensitive) - the independent, index-wide
    definition of "the answer actually exists in the corpus", used to tell
    a retrieval failure (chunk exists, wasn't retrieved/used) apart from a
    not-in-corpus question (no chunk has it at all)."""
    if not expected_tokens:
        return []
    store.ensure_loaded()
    chunks = store._state["chunks"]
    metadata = store._state["metadata"]
    hits = []
    for idx, text in enumerate(chunks):
        low = text.lower()
        if all(tok.lower() in low for tok in expected_tokens):
            hits.append(metadata[idx]["chunk_id"])
    return hits


def _rrf_rank_of(chunk_ids_wanted, candidates):
    """Re-rank `candidates` (each already carrying the app's blended
    `score` and `lexical_overlap`) by classic Reciprocal Rank Fusion over
    those two independent signals, and return the 1-based rank of the
    first candidate whose chunk_id is in chunk_ids_wanted, or None."""
    if not candidates:
        return None
    by_score = sorted(candidates, key=lambda r: -r["score"])
    by_lexical = sorted(candidates, key=lambda r: -r["lexical_overlap"])
    score_rank = {r["chunk_id"]: i + 1 for i, r in enumerate(by_score)}
    lexical_rank = {r["chunk_id"]: i + 1 for i, r in enumerate(by_lexical)}
    fused = sorted(
        candidates,
        key=lambda r: -(1 / (RRF_K + score_rank[r["chunk_id"]])
                         + 1 / (RRF_K + lexical_rank[r["chunk_id"]])),
    )
    for i, r in enumerate(fused, start=1):
        if r["chunk_id"] in chunk_ids_wanted:
            return i
    return None


def retrieval_diagnosis(case, trace, store):
    """Retrieval diagnostics for an expect="answer" case, computed
    regardless of pass/fail (needed for MRR, which is a retrieval-quality
    metric independent of whether the final answer happened to pass):

    - ground_truth_chunk_ids: every chunk anywhere in the index containing
      every expected token - the answer that says "the fact IS indexed".
    - retrieved_rank: 1-based rank of the first such chunk under the app's
      own blended ranking, searched DIAGNOSTIC_DEPTH deep (independent of
      how many chunks were actually handed to the generator).
    - rrf_rank: 1-based rank of the first such chunk under a classic
      Reciprocal Rank Fusion of the app's score-rank and lexical-overlap-
      rank, instead of the app's own blend - a check on whether a textbook
      fusion would have done better or worse here.
    - context_hit: whether a ground-truth chunk was among the chunks
      actually handed to the generator (trace.generation.context_chunk_ids).
    """
    expected_tokens = case.get("expected_tokens", [])
    ground_truth = _ground_truth_chunk_ids(store, expected_tokens)
    candidates = store.search(case["question"], top_k=DIAGNOSTIC_DEPTH)

    retrieved_rank = None
    for i, r in enumerate(candidates, start=1):
        if r["chunk_id"] in ground_truth:
            retrieved_rank = i
            break
    rrf_rank = _rrf_rank_of(set(ground_truth), candidates)

    context_ids = set(trace["generation"]["context_chunk_ids"])
    context_hit = bool(context_ids & set(ground_truth))

    return {
        "ground_truth_chunk_ids": ground_truth,
        "retrieved_rank": retrieved_rank,
        "rrf_rank": rrf_rank,
        "context_hit": context_hit,
    }


def classify_failure(case, payload, diagnosis):
    """Why a case didn't pass, given its (already-computed) retrieval
    diagnosis:

    - "over_answering": an unsupported_question expected a refusal but the
      system answered instead - an answerability-gate miss, not a
      retrieval problem.
    - "not_in_corpus": no chunk anywhere in the index contains every
      expected token - the fact genuinely isn't indexed; no retrieval
      change could fix this case.
    - "retrieval_failure": a chunk containing the answer exists in the
      index, but it never made it into the generator's context - the
      generator never had a chance to use it.
    - "generation_failure": a chunk containing the answer WAS in the
      generator's context, but the final answer still didn't include it -
      retrieval worked; extraction/generation is what failed. This is the
      "the answer was in the chunk but the model couldn't get it" case.
    """
    if case["expect"] == "refuse":
        return "over_answering"
    if not diagnosis["ground_truth_chunk_ids"]:
        return "not_in_corpus"
    if not diagnosis["context_hit"]:
        return "retrieval_failure"
    return "generation_failure"


def run_case(case, store):
    payload, trace = ask_sync(case["question"], generator="extractive",
                               store=store, surface="eval")
    answer = payload["answer"]
    refused = payload["refused"]

    if case["expect"] == "refuse":
        app_pass = refused
        diagnosis = {"ground_truth_chunk_ids": [], "retrieved_rank": None,
                     "rrf_rank": None, "context_hit": None}
    else:
        app_pass = (not refused) and all(
            tok.lower() in answer.lower() for tok in case.get("expected_tokens", []))
        diagnosis = retrieval_diagnosis(case, trace, store)

    diagnosis["failure_type"] = "pass" if app_pass else classify_failure(case, payload, diagnosis)

    return {
        "id": case["id"],
        "mode": case["mode"],
        "question": case["question"],
        "answer": answer,
        "refused": refused,
        "expect": case["expect"],
        "app_pass": app_pass,
        "assertions": deterministic_assertions(case, answer),
        "diagnosis": diagnosis,
    }


def main():
    cases = json.loads(open(CASES_PATH, encoding="utf-8").read())["cases"]
    store = _ensure_index_built()

    results = [run_case(c, store) for c in cases]

    by_mode = defaultdict(list)
    for r in results:
        by_mode[r["mode"]].append(r)

    total_pass = sum(r["app_pass"] for r in results)

    assertion_names = ("code_sample_parses", "endpoint_exists",
                        "api_version_stated", "deprecated_symbol_migration")
    assertion_summary = {}
    for name in assertion_names:
        vals = [r["assertions"][name] for r in results]
        applicable = [v for v in vals if v is not None]
        assertion_summary[name] = {
            "applicable": len(applicable),
            "passed": sum(1 for v in applicable if v),
            "failed": sum(1 for v in applicable if not v),
            "na": len(vals) - len(applicable),
        }

    answerable = [r for r in results if r["expect"] == "answer"]
    mrr_terms = [1 / r["diagnosis"]["retrieved_rank"]
                 if r["diagnosis"]["retrieved_rank"] else 0.0 for r in answerable]
    rrf_terms = [1 / r["diagnosis"]["rrf_rank"]
                 if r["diagnosis"]["rrf_rank"] else 0.0 for r in answerable]
    mrr = round(sum(mrr_terms) / len(mrr_terms), 3) if mrr_terms else None
    rrf_mrr = round(sum(rrf_terms) / len(rrf_terms), 3) if rrf_terms else None

    failure_counts = defaultdict(int)
    for r in results:
        failure_counts[r["diagnosis"]["failure_type"]] += 1

    out = {
        "cases": len(results),
        "application_pass": total_pass,
        "application_pass_rate": round(total_pass / len(results) * 100, 1),
        "by_mode": {
            mode: {
                "pass": sum(r["app_pass"] for r in rows),
                "total": len(rows),
                "rate": round(sum(r["app_pass"] for r in rows) / len(rows) * 100, 1),
            }
            for mode, rows in sorted(by_mode.items())
        },
        "deterministic_assertions": assertion_summary,
        "judged_criteria": 1,
        "retrieval_metrics": {
            "mrr": mrr,
            "rrf_mrr": rrf_mrr,
            "answerable_cases": len(answerable),
            "note": "MRR/RRF are computed only over expect=answer cases, "
                    "searched DIAGNOSTIC_DEPTH=%d deep against the whole "
                    "index, independent of what the generator actually saw."
                    % DIAGNOSTIC_DEPTH,
        },
        "failure_breakdown": dict(sorted(failure_counts.items())),
        "results": results,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print("Track E - one-command eval")
    print(f"cases: {out['cases']} | application pass: {total_pass}/{len(results)} "
          f"= {out['application_pass_rate']}%")
    print(f"MRR: {mrr} | RRF-MRR: {rrf_mrr} (over {len(answerable)} answerable cases)")
    print()
    print("mode\tpass\ttotal\trate")
    for mode, m in out["by_mode"].items():
        print(f"{mode}\t{m['pass']}\t{m['total']}\t{m['rate']}%")
    print()
    print("deterministic assertions (applicable / passed / failed / n_a)")
    for name, s in assertion_summary.items():
        print(f"{name}\t{s['applicable']}\t{s['passed']}\t{s['failed']}\t{s['na']}")
    print()
    print("failure breakdown")
    for ftype, count in out["failure_breakdown"].items():
        print(f"{ftype}\t{count}")
    print()
    print(f"Wrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
