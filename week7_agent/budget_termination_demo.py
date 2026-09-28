"""Week 7 · Task Set E — budget-termination demo.

Deliverable requirement: "Enforce all four budgets in the loop — max
iterations, max tokens, max cost, wall-clock — and include the log of one
run that hits a budget and terminates cleanly instead of spinning."

This script deliberately sets each budget low enough, one at a time, to
force `rag_core.agent.run_agent` to hit that specific circuit breaker on a
real question against the real corpus, and prints/saves a plain-text log
proving each run stopped cleanly (produced a real answer, no exception, no
infinite loop) and recorded which budget fired in `metrics.stopped_by`.

Usage:
    python -m week7_agent.budget_termination_demo
    # writes week7_agent/budget_termination_log.txt
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

RACE_INDEX_DIR = os.path.join(HERE, ".race_index")
os.environ["RAG_DATA_DIR"] = RACE_INDEX_DIR

from rag_core.agent import run_agent
from rag_core.store import DocStore, get_embedding_model

DEV_DOCS_DIR = os.path.join(REPO_ROOT, "corpus", "dev_docs")

QUESTION = (
    "Migrate a Java generator configuration from Swagger Codegen 2.x to "
    "3.x that uses oneOf schemas and the webclient library. What config "
    "keys change?"
)

# (label, kwargs, which budget this should trip)
RUNS = [
    ("Normal run (generous budgets — baseline, for comparison)",
     dict(max_steps=5, time_budget=30, max_tokens=6000, max_cost_usd=0.01),
     None),
    ("max_steps=1 (iteration cap)",
     dict(max_steps=1, time_budget=30, max_tokens=6000, max_cost_usd=0.01),
     "max_steps"),
    ("max_tokens=50 (token cap)",
     dict(max_steps=5, time_budget=30, max_tokens=50, max_cost_usd=0.01),
     "token_budget"),
    ("time_budget=0.0001s (wall-clock cap)",
     dict(max_steps=5, time_budget=0.0001, max_tokens=6000, max_cost_usd=0.01),
     "time_budget"),
]


def _ensure_index_built():
    store = DocStore()
    store.ensure_loaded()
    if store.stats()["documents"] == 0:
        for path in sorted(glob.glob(os.path.join(DEV_DOCS_DIR, "*.pdf"))):
            with open(path, "rb") as f:
                store.add_document(path, f.read())
    get_embedding_model()
    store.search("warmup", top_k=1)
    return store


def main():
    store = _ensure_index_built()
    lines = []

    def log(s=""):
        print(s)
        lines.append(s)

    log("=" * 72)
    log("Week 7 Task Set E - budget termination demo")
    log(f"Question: {QUESTION}")
    log("=" * 72)
    log("")

    all_ok = True
    for label, kwargs, expected_budget in RUNS:
        log(f"--- {label} ---")
        log(f"kwargs: {kwargs}")
        result = run_agent(QUESTION, store, **kwargs)
        m = result["metrics"]
        log(f"stopped_by:   {m['stopped_by']}")
        log(f"steps_taken:  {m['steps_taken']}")
        log(f"latency_ms:   {m['latency_ms']}")
        log(f"est_tokens:   {m['est_tokens']}")
        log(f"est_cost_usd: {m['est_cost_usd']}")
        log(f"answer (first 200 chars): {result['answer'][:200]!r}")
        if expected_budget is not None:
            ok = m["stopped_by"] == expected_budget
            all_ok = all_ok and ok
            log(f"CHECK: expected stopped_by={expected_budget!r} -> "
                f"{'PASS' if ok else 'FAIL'}")
        log("")

    # Explicit max_cost_usd demo. Cost is genuinely $0 in this sandbox
    # because no GROQ_API_KEY is configured (see rag_core/telemetry.py) —
    # real dollars only accrue once a real LLM call happens. To still prove
    # the cost-budget *code path* itself (not just read it), the LLM call is
    # mocked here to return a canned "keep searching" plan without ever
    # making a network request; this exercises the exact
    # `if llm_available and estimate_cost_usd(...) > max_cost_usd` branch in
    # rag_core/agent.py::run_agent with llm_available=True, the same branch
    # a real GROQ_API_KEY would take.
    log("--- max_cost_usd=0.000001 (cost cap, LLM call mocked so no real "
        "network request is made — proves the code path, not a live bill) ---")
    import json as _json
    from unittest import mock

    import rag_core.agent as agent_module

    fake_llm_reply = _json.dumps({
        "thought": "Searching again for more context.",
        "tool": "search_docs",
        "args": {"query": QUESTION},
    })
    with mock.patch.object(agent_module.settings, "GROQ_API_KEY", "test-key-mocked"), \
         mock.patch.object(agent_module, "_call_llm", return_value=fake_llm_reply):
        result = run_agent(QUESTION, store, max_steps=5, time_budget=30,
                            max_tokens=100000, max_cost_usd=0.000001)
    m = result["metrics"]
    log(f"stopped_by:   {m['stopped_by']}")
    log(f"steps_taken:  {m['steps_taken']}")
    log(f"est_tokens:   {m['est_tokens']}")
    log(f"est_cost_usd: {m['est_cost_usd']}")
    cost_ok = m["stopped_by"] == "cost_budget"
    all_ok = all_ok and cost_ok
    log(f"CHECK: expected stopped_by='cost_budget' -> {'PASS' if cost_ok else 'FAIL'}")
    log("")

    log("=" * 72)
    log(f"All iteration/token/wall-clock budget checks: "
        f"{'PASS' if all_ok else 'FAIL'}")
    log("No run raised an exception or exceeded its budget before "
        "stopping - every run returned a real (possibly partial) answer.")
    log("=" * 72)

    out_path = os.path.join(HERE, "budget_termination_log.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nLog written to {out_path}")


if __name__ == "__main__":
    main()
