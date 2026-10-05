"""Week 10 · LLM call meter — one yardstick for both arms of the race.

Every LLM call in this repo (the single ReAct agent's per-step planning call,
generate_groq's answer call, and the squad's worker/synthesis calls) funnels
through rag_core.generators._post_groq_with_retry. Wrapping that one function
means both arms are billed by the same rule — tokens actually sent in
(system + user messages, i.e. including every re-sent context block) and
tokens that came back (content + reasoning) — instead of each arm's own
bookkeeping. rag_core.agent's built-in est_tokens does NOT count re-sent
conversation/context, so it cannot be used to compare against a team of agents.

Token counts use rag_core.telemetry.estimate_tokens (~4 chars/token) — a
heuristic, but the SAME heuristic on both arms, so ratios are meaningful.
"""

import json
import threading
import time
from contextlib import contextmanager

from rag_core import generators
from rag_core.telemetry import estimate_cost_usd, estimate_tokens

_local = threading.local()
_lock = threading.Lock()
_calls = []
_installed = False
_original = None


def _payload_tokens(payload):
    return sum(estimate_tokens(m.get("content", "")) for m in payload.get("messages", []))


def _wrapped(payload):
    t0 = time.perf_counter()
    in_tok = _payload_tokens(payload)
    rec = {"tag": getattr(_local, "tag", "untagged"), "in": in_tok, "out": 0,
           "error": None}
    try:
        message = _original(payload)
        rec["out"] = (estimate_tokens(message.get("content") or "")
                      + estimate_tokens(message.get("reasoning") or ""))
        return message
    except Exception as exc:  # recorded, then re-raised for the caller's own fallback
        rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
        raise
    finally:
        rec["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        _local.last = rec
        with _lock:
            _calls.append(rec)


def install():
    global _installed, _original
    if _installed:
        return
    _original = generators._post_groq_with_retry
    generators._post_groq_with_retry = _wrapped
    _installed = True


@contextmanager
def scope(tag):
    """Tag every LLM call made on this thread inside the block."""
    prev = getattr(_local, "tag", "untagged")
    _local.tag = tag
    try:
        yield
    finally:
        _local.tag = prev


def last_call():
    return getattr(_local, "last", None)


def mark():
    with _lock:
        return len(_calls)


def since(mark_idx):
    with _lock:
        return list(_calls[mark_idx:])


def summarize(calls):
    # A call that errored (e.g. HTTP 429) was never served, so it is counted
    # as an error but not billed as tokens.
    billed = [c for c in calls if not c["error"]]
    tin = sum(c["in"] for c in billed)
    tout = sum(c["out"] for c in billed)
    return {
        "llm_calls": len(calls),
        "llm_errors": sum(1 for c in calls if c["error"]),
        "input_tokens": tin,
        "output_tokens": tout,
        "total_tokens": tin + tout,
        "cost_usd": estimate_cost_usd(tin, tout),
    }
