"""Replay one trace from the trace record ALONE and diff against the original.

Replay contract: everything needed to reproduce the turn must live in the
trace itself - question, retrieval params, embedding model, index state,
generator identity + params. The only external dependency is the index on
disk, whose size is asserted against trace.retrieval.index_chunk_count.

Pick the trace with the same seeded rule documented in notes.md:
    random.Random(SEED).choice(sorted_sample_ids)

Usage:
    python -m week5_error_analysis.replay_trace [--trace-id tr_xxx]
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20260824

from rag_core import settings
from rag_core.pipeline import get_store
from rag_core.generators import GENERATORS
from rag_core.tracing import read_traces


def load_trace(trace_id):
    traces = {t["trace_id"]: t for t in read_traces()}
    if trace_id not in traces:
        raise SystemExit(f"trace_id {trace_id} not found")
    return traces[trace_id]


def replay(trace, store):
    ret = trace["retrieval"]
    results = store.search(trace["question"], top_k=ret["top_k"],
                           min_score=ret["min_score"])
    gen = GENERATORS["extractive"](trace["question"], results)
    return results, gen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-id", default=None)
    args = parser.parse_args()

    sample = json.load(open(os.path.join(HERE, "traces", "sample_20.json"),
                            encoding="utf-8"))
    trace_id = args.trace_id
    if not trace_id:
        ids = sorted(sample["trace_ids"])
        trace_id = random.Random(SEED).choice(ids)
        print(f"Seeded selection: Random({SEED}).choice({len(ids)} ids) "
              f"-> {trace_id}")

    trace = load_trace(trace_id)
    store = get_store()
    stats = store.stats()

    print(f"\nOriginal : {trace['question']}")
    print(f"Index now: {stats['chunks']} chunks | "
          f"trace recorded: {trace['retrieval']['index_chunk_count']} chunks")
    index_ok = stats["chunks"] == trace["retrieval"]["index_chunk_count"]
    print(f"Index state matches trace record: {index_ok}")

    results, gen = replay(trace, store)

    orig_chunks = [r["chunk_id"] for r in trace["retrieval"]["retrieved"]]
    replay_chunks = [r["chunk_id"] for r in results]
    orig_scores = [r["score"] for r in trace["retrieval"]["retrieved"]]
    replay_scores = [r["score"] for r in results]

    same_retrieval = orig_chunks == replay_chunks
    same_output = trace["raw_output"].strip() == gen["answer"].strip()
    scores_close = all(abs(a - b) < 1e-3 for a, b in zip(orig_scores,
                                                         replay_scores))

    print("\n--- ORIGINAL TRACE -------------------------------------------")
    for cid, sc in zip(orig_chunks, orig_scores):
        print(f"  {sc:.4f}  {cid}")
    print("RAW OUTPUT:")
    print("  " + "\n  ".join(trace["raw_output"].splitlines())[:1500])

    print("\n--- REPLAYED FROM TRACE ALONE --------------------------------")
    for r in results:
        print(f"  {r['score']:.4f}  {r['chunk_id']}")
    print("RAW OUTPUT:")
    print("  " + "\n  ".join(gen["answer"].splitlines())[:1500])

    print("\n--- VERDICT --------------------------------------------------")
    print(f"  retrieval identical : {same_retrieval}")
    print(f"  scores within 1e-3  : {scores_close}")
    print(f"  output identical    : {same_output}")

    evidence_path = os.path.join(HERE, "replay_evidence.json")
    evidence = {
        "seed": SEED,
        "trace_id": trace_id,
        "index_state_matches": bool(index_ok),
        "retrieval_identical": bool(same_retrieval),
        "scores_within_tolerance": bool(scores_close),
        "output_identical": bool(same_output),
        "original": {"retrieved": trace["retrieval"]["retrieved"],
                     "raw_output": trace["raw_output"]},
        "replayed": {"retrieved": [{"rank": i, "chunk_id": r["chunk_id"],
                                    "score": r["score"]}
                                   for i, r in enumerate(results, 1)],
                     "raw_output": gen["answer"]},
    }
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)
    print(f"\nEvidence written -> {evidence_path}")


if __name__ == "__main__":
    main()
