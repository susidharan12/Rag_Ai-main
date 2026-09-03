"""Classify each Week 7 trace against expected behaviour and mode outcome.

Expected-value map mirrors the Week 5 battery: every SDK parameter question has
a ground-truth value (v3 by default, v2 when explicitly requested), out-of-corpus
questions must refuse, and the sports set has its golden numbers.
"""
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rag_core.tracing import read_traces

EXPECT = [
 ("What is the default value and type of retry_backoff_ms on Client.send()?", ("500",)),
 ("What is the default timeout_ms for Client.send()?", ("15000",)),
 ("How many times does Client.send() retry by default?", ("max_retries", "5")),
 ("What is the default pool_size for Client.connect()?", ("10",)),
 ("What is the keepalive interval for Client.connect() connections?", ("60000",)),
 ("What is the default tolerance_seconds for webhook verification?", ("300",)),
 ("What is the maximum allowed value of limit in list_events()?", ("200",)),
 ("What is the default page size for list_events()?", ("50",)),
 ("What is the default scope when calling TokenProvider.refresh()?", ("read:events",)),
 ("Is HTTP error code 500 retryable according to the error reference?", ("retryable",)),
 ("What timeout does Client.send() use?", ("15000",)),
 ("How big can the pool be when I connect my client?", ("10",)),
 ("What's the backoff between retries when a send fails?", ("500",)),
 ("How many events can I fetch per page?", ("50",)),
 ("What retries do I get on send?", ("max_retries", "5")),
 ("Does connect need an api key and what regions exist?", ("nk_",)),
 ("In Nimbus SDK v2, what is the default retry_backoff_ms on Client.send()?", ("250",)),
 ("For SDK v2, what pool_size does Client.connect() use by default?", ("5",)),
 ("Is SDK v2 still supported?", ("maintenance",)),
 ("In v2, what happens if I exceed the connection pool quota?", ("POOL_QUOTA",)),
 ("Is HTTP error code 429 (RATE_LIMITED) retryable according to the error reference?", ("retryable",)),
 ("Which error code does the gateway return when the connection pool quota is exceeded?", ("POOL_QUOTA",)),
 ("According to the docs, what changed for timeout_ms between v2 and v3?", ("30000", "15000")),
 ("How many players per side in Football (Soccer)?", ("11",)),
 ("What is the shot clock limit in the NBA?", ("24",)),
 ("How many points is a try worth in Rugby Union?", ("5",)),
 ("What is the men's volleyball net height?", ("2.43",)),
 ("How many holes in a standard golf course?", ("18",)),
 ("How many rounds in a professional boxing bout?", ("12",)),
 ("What governing body oversees international Badminton?", ("BWF",)),
 ("What is the approximate distance of a Formula 1 Grand Prix?", ("305",)),
 ("How many players per side in Kabaddi?", ("7",)),
 ("How many overs in a T20 cricket match?", ("20",)),
 ("What are the four competitive swimming strokes?", ("Freestyle",)),
 ("How many periods in an ice hockey game?", ("3",)),
 ("What is the rate limit, in requests per second, for the /v3/events/stream endpoint?", "refuse"),
 ("What is the default retry backoff for the Nimbus SDK's Go client?", "refuse"),
 ("What is the maximum webhook payload size accepted by WebhookVerifier?", "refuse"),
 ("Who won the 1998 FIFA World Cup final?", "refuse"),
 ("How do I deploy the Nimbus gateway to Kubernetes?", "refuse"),
]

def classify(traces):
    rows = []
    by_q = {t["question"]: t for t in traces}
    for q, want in EXPECT:
        t = by_q[q]
        ans = t["raw_output"]
        refused = t["refused"]
        if want == "refuse":
            ok = refused
        else:
            ok = (not refused) and all(w.lower() in ans.lower() for w in want)
        rows.append((q, want, refused, ok, ans))
    return rows

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "week6_error_analysis/traces/battery.ndjson"
    rows = classify(read_traces(path))
    passed = sum(1 for q, want, refused, ok, ans in rows if ok)
    print(f"correct {passed}/{len(rows)}\n")
    for q, want, refused, ok, ans in rows:
        mark = "PASS" if ok else "FAIL"
        print(f"{mark:4s} | {q[:55]:55s} | want={want if want!='refuse' else 'REFUSE'} | {'REFUSED' if refused else ans[:45]}")
