"""Draw a provably random sample of N traces with a documented seed.

The seed is fixed at the top of this file and pasted into notes.md. Anyone
can rerun `python -m week5_error_analysis.sample_traces` and must get the
same 20 trace_ids.
"""

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_core.tracing import read_traces

SEED = 20260824          # yyyymmdd of capture day - pasted into notes.md
SAMPLE_SIZE = 20
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "traces", "sample_20.json")


def main():
    traces = read_traces()
    ids = [t["trace_id"] for t in traces]
    rng = random.Random(SEED)
    sample_ids = sorted(rng.sample(ids, SAMPLE_SIZE))

    by_id = {t["trace_id"]: t for t in traces}
    sample = [by_id[i] for i in sample_ids]

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"seed": SEED, "population": len(ids),
                   "sample_size": SAMPLE_SIZE,
                   "trace_ids": sample_ids}, f, indent=2)

    print(f"SEED={SEED} population={len(ids)} k={SAMPLE_SIZE}")
    for tid in sample_ids:
        q = next(t["question"] for t in traces if t["trace_id"] == tid)
        print(f"  {tid}  {q[:70]}")
    print(f"\nWritten -> {OUT_PATH}")


if __name__ == "__main__":
    main()
