"""Week 4 Task Set E — Evaluation Script (PDF pipeline)

Measures hit-rate@3 on a 12-question golden set before and after exactly
one retrieval change (cross-encoder rerank over dense top-25). Also
measures p50 latency per query and labels every miss as R / G / Not-In-Corpus.
"""

import json
import statistics
import time
import pickle
import os
import re
import sys

import faiss
import numpy as np
from sentence_transformers import CrossEncoder

import config
from pdf_reader import get_embedding_model

CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

GOLDEN_SET_PATH = "golden_set.jsonl"
RESULTS_PATH = "results.md"


# ---------------------------------------------------------------------------
# Load index + chunks (PDF pipeline)
# ---------------------------------------------------------------------------

def load_pdf_index():
    index = faiss.read_index(config.INDEX_PATH)
    with open(config.CHUNKS_PATH, "rb") as f:
        data = pickle.load(f)
    return index, data["chunks"], data["metadata"]


def load_golden_set():
    questions = []
    with open(GOLDEN_SET_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


# ---------------------------------------------------------------------------
# Dense retrieval (baseline)
# ---------------------------------------------------------------------------

def dense_search(query, index, chunks, metadata, top_k=3, return_full=False):
    model = get_embedding_model()
    vec = model.encode([query], convert_to_numpy=True)
    vec = np.array(vec, dtype="float32")
    faiss.normalize_L2(vec)

    n_total = index.ntotal
    distances, indices = index.search(vec, n_total)

    full_results = []
    for rank_i, (idx, score) in enumerate(zip(indices[0], distances[0])):
        if idx == -1:
            continue
        full_results.append({
            "rank": len(full_results) + 1,
            "global_pos": int(idx),
            "chunk_index": int(idx),
            "chunk": chunks[idx],
            "metadata": metadata[idx],
            "score": float(score),
        })

    if return_full:
        return full_results
    return full_results[:top_k]


# ---------------------------------------------------------------------------
# Cross-encoder rerank
# ---------------------------------------------------------------------------

_cross_encoder = None

def get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        print("  Loading cross-encoder model...")
        _cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)
    return _cross_encoder


def cross_encoder_rerank(query, dense_results, top_k=3):
    """Re-rank dense top-25 results with a cross-encoder, return top_k."""
    if not dense_results:
        return []

    ce = get_cross_encoder()
    pairs = [(query, r["chunk"]) for r in dense_results]
    ce_scores = ce.predict(pairs)

    for r, score in zip(dense_results, ce_scores):
        r["ce_score"] = float(score)

    reranked = sorted(dense_results, key=lambda r: r["ce_score"], reverse=True)

    results = []
    for rank_i, r in enumerate(reranked[:top_k]):
        results.append({
            "rank": rank_i + 1,
            "global_pos": r["global_pos"],
            "chunk_index": r["global_pos"],
            "chunk": r["chunk"],
            "metadata": r["metadata"],
            "score": r["ce_score"],
        })
    return results


# ---------------------------------------------------------------------------
# Evaluation core
# ---------------------------------------------------------------------------

def hit_in_top_k(results, expected_chunk_pos, top_k=3):
    """Check if expected chunk position (int) appears in top-k results."""
    for r in results[:top_k]:
        if r["chunk_index"] == expected_chunk_pos:
            return True
    return False


def measure_latency(fn, n_runs=5):
    """Run fn() n_runs times, return (median_ms, all_times_ms)."""
    times = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)
    return statistics.median(times), times


def run_evaluation(questions, search_fn, label=""):
    """Run all questions through search_fn, return per-question results."""
    results = []
    hits = 0
    latencies = []

    for q in questions:
        def do_search():
            return search_fn(q["question"])

        median_ms, all_ms = measure_latency(do_search, n_runs=5)
        res = do_search()
        # Get full ranked list for failure analysis
        full_res = search_fn(q["question"]) if hasattr(search_fn, '__name__') and 'dense' in search_fn.__name__ else res
        hit = hit_in_top_k(res, q["known_chunk"], top_k=3)
        hits += int(hit)
        latencies.append(median_ms)

        top3_indices = [r["metadata"]["chunk_index"] for r in res[:3]]
        top3_pages = [r["metadata"]["page_number"] for r in res[:3]]
        top3_scores = [round(r["score"], 4) for r in res[:3]]

        results.append({
            "id": q["id"],
            "question": q["question"],
            "known_chunk": q["known_chunk"],
            "hit": hit,
            "top3_indices": top3_indices,
            "top3_pages": top3_pages,
            "top3_scores": top3_scores,
            "latency_ms": round(median_ms, 2),
            "all_results": res,
        })

    hit_rate = hits / len(questions)
    p50_latency = statistics.median(latencies)

    return {
        "label": label,
        "hit_rate": hit_rate,
        "hits": hits,
        "total": len(questions),
        "p50_latency_ms": round(p50_latency, 2),
        "per_question": results,
    }


# ---------------------------------------------------------------------------
# Inspection view — label failures
# ---------------------------------------------------------------------------

def label_failures(eval_result, questions, chunks, metadata):
    """For every question, label R/G/Not-In-Corpus based on retrieval status."""
    # Build a map from global_pos to metadata
    pos_map = {i: (chunks[i], metadata[i]) for i in range(len(metadata))}

    labels = []
    for qr in eval_result["per_question"]:
        if qr["hit"]:
            labels.append({
                "id": qr["id"],
                "label": "G",
                "evidence": "Expected chunk found in top-3 results (guarantee)",
                "known_chunk": qr["known_chunk"],
                "top3_indices": qr["top3_indices"],
                "known_rank_full": 1,
                "evidence_text_preview": "",
            })
            continue

        qid = qr["id"]
        expected_pos = qr["known_chunk"]

        # Use full_results if available
        full_results = qr.get("full_results", qr.get("all_results", []))

        # Check if the known chunk appears ANYWHERE in the full ranked list
        known_in_full = False
        known_rank = None
        for r in full_results:
            if r["global_pos"] == expected_pos:
                known_in_full = True
                known_rank = r["rank"]
                break

        # Check if the known chunk's PAGE is in top-3
        known_page = None
        if expected_pos in pos_map:
            _, meta = pos_map[expected_pos]
            known_page = meta["page_number"]

        page_in_top3 = False
        for r in full_results[:3]:
            if r["metadata"]["page_number"] == known_page:
                page_in_top3 = True
                break

        if known_in_full:
            if page_in_top3:
                evidence = (f"Known chunk pos={expected_pos} (page {known_page}) at rank {known_rank}; "
                           f"its page IS in top-3 via another chunk, "
                           f"but the specific needed chunk missed top-3")
                label = "R"
            else:
                evidence = (f"Known chunk pos={expected_pos} at rank {known_rank} in full list; "
                           f"page {known_page} not in top-3 at all")
                label = "R"
        else:
            if expected_pos in pos_map:
                evidence = (f"Known chunk pos={expected_pos} exists in index but is NOT in "
                           f"any of the {len(full_results)} retrieved results")
                label = "R"
            else:
                evidence = f"Known chunk pos={expected_pos} does not exist in the index"
                label = "Not-In-Corpus"

        # Find evidence text from the known chunk
        evidence_text = ""
        if expected_pos in pos_map:
            text, _ = pos_map[expected_pos]
            evidence_text = text[:200].replace("\n", " ")

        labels.append({
            "id": qid,
            "label": label,
            "evidence": evidence,
            "known_chunk": expected_pos,
            "top3_indices": qr["top3_indices"],
            "known_rank_full": known_rank,
            "evidence_text_preview": evidence_text,
        })

    return labels


# ---------------------------------------------------------------------------
# Format results as markdown
# ---------------------------------------------------------------------------

def format_results_table(baseline, hybrid):
    """Format before/after comparison table."""
    lines = []
    lines.append("| Metric | Before (Dense) | After (CE-Rerank) | Delta |")
    lines.append("|--------|:--------------:|:-----------------:|:-----:|")
    lines.append(f"| Hit-rate@3 | {baseline['hit_rate']:.2f} ({baseline['hits']}/{baseline['total']}) | "
                 f"{hybrid['hit_rate']:.2f} ({hybrid['hits']}/{hybrid['total']}) | "
                 f"{hybrid['hit_rate'] - baseline['hit_rate']:+.2f} |")
    lines.append(f"| p50 latency (ms) | {baseline['p50_latency_ms']:.1f} | "
                 f"{hybrid['p50_latency_ms']:.1f} | "
                 f"{hybrid['p50_latency_ms'] - baseline['p50_latency_ms']:+.1f} |")
    return "\n".join(lines)


def format_per_question_table(baseline, hybrid):
    """Per-question fixed/unfixed/still-broken table."""
    lines = []
    lines.append("| ID | Question (short) | Known chunk | Dense top-3 | RRF top-3 | Dense hit | RRF hit | Status |")
    lines.append("|----|------------------|-------------|-------------|-----------|:---------:|:-------:|:------:|")

    b_map = {r["id"]: r for r in baseline["per_question"]}
    h_map = {r["id"]: r for r in hybrid["per_question"]}

    for qid in [r["id"] for r in baseline["per_question"]]:
        b = b_map[qid]
        h = h_map[qid]
        short_q = b["question"][:50] + ("..." if len(b["question"]) > 50 else "")
        b_top3 = ", ".join(b["top3_ids"][:3])
        h_top3 = ", ".join(h["top3_ids"][:3])
        b_hit = "Y" if b["hit"] else "N"
        h_hit = "Y" if h["hit"] else "N"

        if not b["hit"] and h["hit"]:
            status = "FIXED"
        elif b["hit"] and h["hit"]:
            status = "OK"
        elif b["hit"] and not h["hit"]:
            status = "REGRESSED"
        else:
            status = "STILL-BROKEN"

        lines.append(f"| {qid} | {short_q} | `{b['known_chunk_id']}` | {b_top3} | {h_top3} | {b_hit} | {h_hit} | {status} |")

    return "\n".join(lines)


def format_failure_labels(labels):
    """Format the R/G/Not-In-Corpus tally."""
    lines = []
    tally = {"R": 0, "G": 0, "Not-In-Corpus": 0}
    for lb in labels:
        tally[lb["label"]] += 1

    lines.append(f"**Tally:** G={tally['G']}, R={tally['R']}, Not-In-Corpus={tally['Not-In-Corpus']}")
    lines.append("")
    lines.append("| ID | Label | Evidence |")
    lines.append("|----|-------|----------|")
    for lb in labels:
        evidence_short = lb["evidence"][:120]
        lines.append(f"| {lb['id']} | **{lb['label']}** | {evidence_short} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Week 4 Task Set E — Evaluation (PDF pipeline)")
    print("=" * 70)

    # Load everything
    print("\nLoading PDF index and golden set...")
    index, chunks, metadata = load_pdf_index()
    questions = load_golden_set()
    print(f"  Chunks: {len(chunks)}, Questions: {len(questions)}")

    # --- BASELINE: dense only ---
    print("\n--- BASELINE: Dense retrieval (top-3) ---")
    def dense_search_q(query):
        return dense_search(query, index, chunks, metadata, top_k=3)

    def dense_search_q_full(query):
        return dense_search(query, index, chunks, metadata, top_k=3, return_full=True)

    baseline = run_evaluation(questions, dense_search_q, label="Dense")
    
    # Also get full ranked lists for failure analysis
    for qr in baseline["per_question"]:
        full_res = dense_search_q_full(qr["question"])
        qr["full_results"] = full_res

    print(f"  Hit-rate@3: {baseline['hit_rate']:.2f} ({baseline['hits']}/{baseline['total']})")
    print(f"  p50 latency: {baseline['p50_latency_ms']:.1f} ms")

    for r in baseline["per_question"]:
        mark = "HIT" if r["hit"] else "MISS"
        status = "G" if r["hit"] else "R"
        print(f"  {r['id']}: {mark}  [{status}]  top3={r['top3_indices'][:3]} pages={r['top3_pages'][:3]}")

    # --- Label failures on baseline ---
    print("\n--- RETRIEVAL LABELS (baseline) ---")
    labels = label_failures(baseline, questions, chunks, metadata)
    for lb in labels:
        print(f"  {lb['id']}: [{lb['label']}] {lb['evidence'][:120]}")

    # --- AFTER: Cross-encoder rerank over dense top-25 ---
    print("\n--- AFTER: Cross-encoder rerank over dense top-25 ---")
    def hybrid_search_q(query):
        dense_res = dense_search(query, index, chunks, metadata, top_k=25)
        return cross_encoder_rerank(query, dense_res, top_k=3)

    hybrid = run_evaluation(questions, hybrid_search_q, label="CE-Rerank")
    print(f"  Hit-rate@3: {hybrid['hit_rate']:.2f} ({hybrid['hits']}/{hybrid['total']})")
    print(f"  p50 latency: {hybrid['p50_latency_ms']:.1f} ms")

    for r in hybrid["per_question"]:
        mark = "HIT" if r["hit"] else "MISS"
        status = "G" if r["hit"] else "R"
        print(f"  {r['id']}: {mark}  [{status}]  top3={r['top3_indices'][:3]} pages={r['top3_pages'][:3]}")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Before (Dense):  hit@3 = {baseline['hit_rate']:.2f}  p50 = {baseline['p50_latency_ms']:.1f} ms")
    print(f"After  (CE):     hit@3 = {hybrid['hit_rate']:.2f}  p50 = {hybrid['p50_latency_ms']:.1f} ms")
    delta = hybrid['hit_rate'] - baseline['hit_rate']
    print(f"Delta:           hit@3 = {delta:+.2f}  p50 = {hybrid['p50_latency_ms'] - baseline['p50_latency_ms']:+.1f} ms")

    # --- Dump JSON for reference ---
    dump = {
        "baseline": {
            "hit_rate": baseline["hit_rate"],
            "p50_latency_ms": baseline["p50_latency_ms"],
            "per_question": [{k: v for k, v in r.items() if k != "all_results"} for r in baseline["per_question"]],
        },
        "hybrid": {
            "hit_rate": hybrid["hit_rate"],
            "p50_latency_ms": hybrid["p50_latency_ms"],
            "per_question": [{k: v for k, v in r.items() if k != "all_results"} for r in hybrid["per_question"]],
        },
        "failure_labels": labels,
    }
    with open("week4_eval_dump.json", "w") as f:
        json.dump(dump, f, indent=2)
    print("\nDumped to week4_eval_dump.json")

    return baseline, hybrid, labels


if __name__ == "__main__":
    baseline, hybrid, labels = main()
