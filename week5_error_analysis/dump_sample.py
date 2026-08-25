"""Dump full detail of sampled traces for open-coding."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_core.tracing import read_traces

HERE = os.path.dirname(os.path.abspath(__file__))
sample = json.load(open(os.path.join(HERE, "traces", "sample_20.json"),
                        encoding="utf-8"))
by_id = {t["trace_id"]: t for t in read_traces()}

for tid in sample["trace_ids"]:
    t = by_id[tid]
    print("=" * 100)
    print(tid, "|", t["question"])
    for r in t["retrieval"]["retrieved"]:
        print("   #{rank} {score:.4f} {cid:48s} v={ver!r:6s} p{pg}".format(
            rank=r["rank"], score=r["score"], cid=r["chunk_id"],
            ver=r["sdk_version"], pg=r["page_number"]))
    print("OUT:", " ".join(t["raw_output"].split())[:700])
