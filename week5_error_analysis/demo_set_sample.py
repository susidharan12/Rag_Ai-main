"""Bonus: the CURATED demo set - the 10 questions always shown at the DX
review - run through the identical pipeline so its traces can be labelled
with the same failure-mode rubric as the random sample."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.abspath(__file__))

DEMO_QUESTIONS = [
    "What is the default value and type of retry_backoff_ms on Client.send()?",
    "What is the default pool_size for Client.connect()?",
    "Is HTTP error code 429 (RATE_LIMITED) retryable according to the error reference?",
    "Show me how to verify a webhook signature in Python.",
    "How many players per side in Football (Soccer)?",
    "What is the shot clock limit in the NBA?",
    "What governing body oversees international Badminton?",
    "What is the maximum allowed value of limit in list_events()?",
    "What is the default timeout_ms for Client.send()?",
    "What is the men's volleyball net height?",
]


def main():
    from rag_core.pipeline import ask_sync, get_store

    store = get_store()
    out = []
    for q in DEMO_QUESTIONS:
        payload, trace = ask_sync(q, generator="extractive",
                                  surface="demo-set", store=store)
        out.append({"trace_id": trace["trace_id"], "question": q,
                    "raw_output": trace["raw_output"],
                    "retrieved": trace["retrieval"]["retrieved"]})
        print("=" * 100)
        print(trace["trace_id"], "|", q)
        for r in trace["retrieval"]["retrieved"]:
            print("   #{rank} {score:.4f} {cid:48s} v={ver!r}".format(
                rank=r["rank"], score=r["score"], cid=r["chunk_id"],
                ver=r["sdk_version"]))
        print("OUT:", " ".join(trace["raw_output"].split())[:500])

    path = os.path.join(HERE, "traces", "demo_set.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\n{len(out)} demo traces -> {path}")


if __name__ == "__main__":
    main()
