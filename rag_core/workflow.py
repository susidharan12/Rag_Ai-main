"""Week 7 · Fixed Workflow — the simple, no-loop baseline.

Task Set E requirement: "re-implement the identical task as a fixed
workflow — hard-coded steps, same tools, same model, same output contract.
No loop." That means this file must call the *exact same* tool functions
the agent uses (`rag_core.agent._execute_tool` / `TOOL_SCHEMAS`), not a
different, simpler retrieval path — the only difference from the agent is
that no model decides which tool to call next. The sequence below always
runs, in this order, for every question:

  1. search_docs        — find the relevant docs page(s)
  2. get_version_info    — read the docs scoped to the target api_version
  3. check_deprecation   — check whether the subject changed/was replaced
                            at that version (the new Task Set E tool)
  4. generate            — synthesize the final answer from everything
                            steps 1-3 retrieved, via the same generator
                            (Groq LLM, or the deterministic extractive
                            fallback) the agent's own answer synthesis uses.

Step 3 always runs, even when the question turns out not to need it — that
asymmetry (the agent's fallback plan skips it when nothing changed; this
workflow never does) is itself part of the cost/latency story the race is
supposed to surface, not a bug to "fix" by making the workflow adaptive.
"""

import time

from rag_core import settings
from rag_core.agent import (
    _execute_tool,
    _extract_subject,
    _extract_versions,
    _pick_target_version,
)
from rag_core.generators import GENERATORS, build_context
from rag_core.telemetry import estimate_cost_usd, estimate_tokens

_DEFAULT_GITHUB_TARGET = "2025-06-01"
_DEFAULT_SWAGGER_TARGET = "3.x"


def _default_target_version(question):
    """Hard-coded fallback target version when the question names none —
    the same "aim at the newer/target version" default a human writing this
    fixed pipeline by hand would pick for a migration-docs assistant."""
    q = question.lower()
    if "swagger" in q or "codegen" in q or ".x" in q:
        return _DEFAULT_SWAGGER_TARGET
    return _DEFAULT_GITHUB_TARGET


def run_workflow(question, store, generator=None, top_k=None):
    """Run the fixed, hard-coded 4-step pipeline (see module docstring).

    Returns:
        {
            "answer": str,
            "refused": bool,
            "steps": [{"step": int, "name": str, "tool": str, "detail": str,
                       "latency_ms": float}],
            "metrics": {
                "latency_ms": float,
                "api_calls": int,
                "chunks_retrieved": int,
                "model": str,
                "est_tokens": int,
                "est_cost_usd": float,
            }
        }
    """
    gen_name = generator or settings.DEFAULT_GENERATOR
    top_k = top_k or settings.TOP_K

    steps = []
    context_results = []
    t_total_start = time.perf_counter()

    versions = _extract_versions(question)
    subject = _extract_subject(question) or "the referenced endpoint or parameter"
    target_version = _pick_target_version(versions) or _default_target_version(question)

    # --- Step 1: search_docs — find the relevant docs page(s) ---
    t0 = time.perf_counter()
    obs1, raw1 = _execute_tool("search_docs", {"query": question}, store)
    context_results.extend(raw1)
    step1_ms = round((time.perf_counter() - t0) * 1000, 1)
    steps.append({
        "step": 1, "name": "find docs page", "tool": "search_docs",
        "detail": f"Retrieved {len(raw1)} chunks for the question.",
        "latency_ms": step1_ms,
    })

    # --- Step 2: get_version_info — read the spec for the target version ---
    t0 = time.perf_counter()
    obs2, raw2 = _execute_tool(
        "get_version_info", {"version": target_version, "query": question}, store
    )
    context_results.extend(raw2)
    step2_ms = round((time.perf_counter() - t0) * 1000, 1)
    steps.append({
        "step": 2, "name": "read version-scoped spec", "tool": "get_version_info",
        "detail": f"Read docs scoped to api_version={target_version} "
                  f"({len(raw2)} chunks).",
        "latency_ms": step2_ms,
    })

    # --- Step 3: check_deprecation — always runs; fixed pipeline, no branch ---
    t0 = time.perf_counter()
    obs3, raw3 = _execute_tool(
        "check_deprecation", {"subject": subject, "api_version": target_version}, store
    )
    context_results.extend(raw3)
    step3_ms = round((time.perf_counter() - t0) * 1000, 1)
    steps.append({
        "step": 3, "name": "check changelog / deprecation", "tool": "check_deprecation",
        "detail": f"Checked whether '{subject}' changed at api_version="
                  f"{target_version} ({len(raw3)} chunks).",
        "latency_ms": step3_ms,
    })

    # De-dupe accumulated chunks by chunk_id before generation (the same
    # chunk can legitimately surface from more than one of the 3 lookups).
    seen_ids = set()
    gen_results = []
    for r in context_results:
        cid = r.get("chunk_id")
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        gen_results.append(r)
    if not gen_results:
        gen_results = store.search(question, top_k=max(top_k, 5))

    # --- Step 4: generate — same model/generator the agent's synthesis uses ---
    t0 = time.perf_counter()
    gen = GENERATORS[gen_name](question, gen_results, store=store)
    if gen.get("error"):
        fallback_note = f"{gen['model']} unavailable ({gen['error']})"
        gen = GENERATORS["extractive"](question, gen_results, store=store)
        gen["model"] = "extractive-v2 (fallback)"
        gen["params"]["fallback"] = fallback_note
    step4_ms = round((time.perf_counter() - t0) * 1000, 1)
    steps.append({
        "step": 4, "name": "generate", "tool": gen["model"],
        "detail": f"Generated the final answer using {gen['model']}.",
        "latency_ms": step4_ms,
    })

    total_ms = round((time.perf_counter() - t_total_start) * 1000, 1)

    # Telemetry: tokens measure content volume moved through the pipeline —
    # the 3 tool observations plus the question and final answer — counted
    # the same way whether or not a real LLM produced that final answer, so
    # this is comparable to the agent's own token accounting (which likewise
    # counts thought/args/observation volume regardless of LLM
    # availability). Cost, unlike tokens, is real dollars: it is genuinely
    # $0 whenever no external API call actually happened (the extractive
    # fallback path) — a real finding, not a placeholder. The 3 retrieval
    # tool calls are always local vector-store lookups (no LLM), same as
    # the agent's own tool calls; only the final generation step is ever
    # billable, and only when it actually hit a real LLM.
    is_llm_call = "extractive" not in gen["model"].lower()
    est_input_tokens = (
        estimate_tokens(obs1) + estimate_tokens(obs2) + estimate_tokens(obs3)
        + estimate_tokens(build_context(gen_results)) + estimate_tokens(question)
    )
    est_output_tokens = estimate_tokens(gen["answer"])
    est_tokens = est_input_tokens + est_output_tokens
    est_cost = estimate_cost_usd(est_input_tokens, est_output_tokens) if is_llm_call else 0.0

    return {
        "answer": gen["answer"],
        "refused": gen["refused"],
        "steps": steps,
        "metrics": {
            "latency_ms": total_ms,
            "retrieve_latency_ms": round(step1_ms + step2_ms + step3_ms, 1),
            "generate_latency_ms": step4_ms,
            "api_calls": 1 if is_llm_call else 0,
            "tool_calls": 3,
            "chunks_retrieved": len(raw1) + len(raw2) + len(raw3),
            "chunks_used": len(gen_results),
            "model": gen["model"],
            "est_tokens": est_tokens,
            "est_cost_usd": est_cost,
        },
    }
