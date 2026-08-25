"""The full RAG turn: retrieve -> generate -> trace."""

import time

from rag_core import settings
from rag_core.generators import GENERATORS
from rag_core.store import DocStore
from rag_core.tracing import new_trace_id, write_trace

_default_store = None


def get_store():
    global _default_store
    if _default_store is None:
        _default_store = DocStore()
    return _default_store


def ask_sync(question, generator=None, top_k=None, min_score=None,
             surface="api", store=None, trace_path=None):
    """Run one full RAG turn synchronously and return (payload, trace)."""

    store = store or get_store()
    gen_name = generator or settings.DEFAULT_GENERATOR
    top_k = top_k or settings.TOP_K

    t0 = time.perf_counter()
    results = store.search(question, top_k=top_k, min_score=min_score)
    t1 = time.perf_counter()

    gen = GENERATORS[gen_name](question, results)
    if gen.get("error"):
        # Generator backend unreachable/failed: degrade gracefully to the
        # deterministic grounded extractor so the product still answers.
        fallback_note = f"{gen['model']} unavailable ({gen['error']})"
        gen = GENERATORS["extractive"](question, results)
        gen["model"] = "extractive-v1 (fallback)"
        gen["params"]["fallback"] = fallback_note
    t2 = time.perf_counter()

    stats = store.stats()
    trace = {
        "trace_id": new_trace_id(),
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "surface": surface,
        "question": question,
        "retrieval": {
            "embedding_model": settings.EMBEDDING_MODEL_NAME,
            "top_k": top_k,
            "min_score": settings.MIN_SCORE if min_score is None else min_score,
            "index_chunk_count": stats["chunks"],
            "documents_indexed": stats["documents"],
            "retrieved": [
                {k: r[k] for k in ("rank", "chunk_id", "score", "source_doc",
                                   "page_number", "sdk_version")}
                for r in results
            ],
            "retrieved_texts": {r["chunk_id"]: r["text"] for r in results},
        },
        "generation": {
            "model": gen["model"],
            "prompt_version": gen["prompt_version"],
            "params": gen["params"],
            "context_chunk_ids": [r["chunk_id"] for r in results],
        },
        "raw_output": gen["answer"],
        "refused": gen["refused"],
        "latency_ms": {
            "retrieve": round((t1 - t0) * 1000, 1),
            "generate": round((t2 - t1) * 1000, 1),
            "total": round((t2 - t0) * 1000, 1),
        },
    }
    write_trace(trace, path=trace_path)

    payload = {
        "trace_id": trace["trace_id"],
        "question": question,
        "answer": gen["answer"],
        "refused": gen["refused"],
        "sources": [
            {"chunk_id": r["chunk_id"], "score": r["score"],
             "source_doc": r["source_doc"], "page_number": r["page_number"],
             "sdk_version": r.get("sdk_version", ""), "snippet": r["text"][:280]}
            for r in results
        ],
        "latency_ms": trace["latency_ms"],
        "index": {"chunks": stats["chunks"], "documents": stats["documents"]},
    }
    return payload, trace


async def ask(*args, **kwargs):
    return ask_sync(*args, **kwargs)
