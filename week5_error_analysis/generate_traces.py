"""Generate the Week 5 trace corpus by running REAL turns through the live
pipeline (real embeddings, real FAISS search, real generator output).

Every question below was written BEFORE looking at any output, grouped by
intent so the capture covers how the assistant is actually used:

  A  v3 factoid questions        - unversioned phrasing, as users really ask
  B  version-ambiguous repeats   - same facts, deliberately no version given
  C  explicit v2 questions       - maintainer on legacy installs
  D  cross-reference traps       - fact mentioned on a page that doesn't own it
  E  sports golden questions     - the Week 4 golden set against the PDF
  F  out-of-corpus               - should refuse
  G  vague / multi-part          - realistic messy asks
  H  code-usage                  - "how do I ..." questions

Usage:
    python -m week5_error_analysis.generate_traces

Default generator is extractive; every answer is a real output of the
running system.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_core import settings
from rag_core.pipeline import ask_sync
from rag_core.tracing import read_traces

QUESTIONS = [
    # ---- A: v3 factoid questions (unversioned phrasing) -----------------
    ("A", "What is the default value and type of retry_backoff_ms on Client.send()?"),
    ("A", "What is the default timeout_ms for Client.send()?"),
    ("A", "How many times does Client.send() retry by default?"),
    ("A", "What is the default pool_size for Client.connect()?"),
    ("A", "What is the keepalive interval for Client.connect() connections?"),
    ("A", "What is the default tolerance_seconds for webhook verification?"),
    ("A", "What is the maximum allowed value of limit in list_events()?"),
    ("A", "What is the default page size for list_events()?"),
    ("A", "What is the default scope when calling TokenProvider.refresh()?"),
    ("A", "Is HTTP error code 500 retryable according to the error reference?"),

    # ---- B: version-ambiguous repeats ------------------------------------
    ("B", "What timeout does Client.send() use?"),
    ("B", "How big can the pool be when I connect my client?"),
    ("B", "What's the backoff between retries when a send fails?"),
    ("B", "How many events can I fetch per page?"),
    ("B", "What retries do I get on send?"),
    ("B", "Does connect need an api key and what regions exist?"),

    # ---- C: explicit v2 questions ------------------------------------------
    ("C", "In Nimbus SDK v2, what is the default retry_backoff_ms on Client.send()?"),
    ("C", "For SDK v2, what pool_size does Client.connect() use by default?"),
    ("C", "Is SDK v2 still supported?"),
    ("C", "In v2, what happens if I exceed the connection pool quota?"),

    # ---- D: cross-reference traps ------------------------------------------
    ("D", "Is HTTP error code 429 (RATE_LIMITED) retryable according to the error reference?"),
    ("D", "Which error code does the gateway return when the connection pool quota is exceeded?"),
    ("D", "According to the docs, what changed for timeout_ms between v2 and v3?"),
    ("D", "Where is the maximum pagination limit documented and what is it?"),

    # ---- E: sports golden set (Week 4) --------------------------------------
    ("E", "How many players per side in Football (Soccer)?"),
    ("E", "What is the shot clock limit in the NBA?"),
    ("E", "How many points is a try worth in Rugby Union?"),
    ("E", "What is the men's volleyball net height?"),
    ("E", "How many holes in a standard golf course?"),
    ("E", "How many rounds in a professional boxing bout?"),
    ("E", "What governing body oversees international Badminton?"),
    ("E", "What is the approximate distance of a Formula 1 Grand Prix?"),
    ("E", "How many players per side in Kabaddi?"),
    ("E", "How many overs in a T20 cricket match?"),
    ("E", "What are the four competitive swimming strokes?"),
    ("E", "How many periods in an ice hockey game?"),

    # ---- F: out-of-corpus -----------------------------------------------------
    ("F", "What is the rate limit, in requests per second, for the /v3/events/stream endpoint?"),
    ("F", "What is the default retry backoff for the Nimbus SDK's Go client?"),
    ("F", "What is the maximum webhook payload size accepted by WebhookVerifier?"),
    ("F", "Who won the 1998 FIFA World Cup final?"),
    ("F", "How do I deploy the Nimbus gateway to Kubernetes?"),

    # ---- G: vague / multi-part --------------------------------------------------
    ("G", "Tell me about Client.send timeouts and retries."),
    ("G", "Explain authentication in the Nimbus SDK including token expiry and scopes."),
    ("G", "Compare v2 and v3 defaults."),

    # ---- H: code usage ------------------------------------------------------------
    ("H", "How do I pass a custom retry_backoff_ms value when constructing the request in code?"),
    ("H", "Show me how to verify a webhook signature in Python."),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", default="extractive",
                        choices=["extractive"])
    parser.add_argument("--out", default=settings.TRACES_PATH)
    args = parser.parse_args()

    store = __import__("rag_core.store", fromlist=["DocStore"]).DocStore()
    stats = store.stats()
    print(f"Index: {stats['documents']} docs, {stats['chunks']} chunks")
    if stats["documents"] == 0:
        print("No documents indexed. Ingest corpus first "
              "(python -m week5_error_analysis.ingest_corpus).")
        sys.exit(1)

    existing = len(read_traces(args.out))
    print(f"Existing traces in {args.out}: {existing}")

    n = 0
    for section, question in QUESTIONS:
        _, trace = ask_sync(question, generator=args.generator,
                            surface=f"battery/{section}", store=store,
                            trace_path=args.out)
        n += 1
        flag = "REFUSED" if trace["refused"] else "ok"
        print(f"[{section}] {flag:7s} {trace['latency_ms']['total']:>7.1f} ms  "
              f"{question[:70]}")

    total = len(read_traces(args.out))
    lines = sum(1 for _ in open(args.out, encoding="utf-8"))
    print(f"\nWrote {n} new traces. File now holds {total} traces, "
          f"{lines} lines -> {args.out}")


if __name__ == "__main__":
    main()
