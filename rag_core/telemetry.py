"""Week 7 · Shared telemetry helpers — token/cost estimation and latency
percentiles, used by both the agent loop and the fixed workflow so the race
compares them on the same units.

Token counts are a heuristic (~4 chars/token), not a real tokenizer count —
good enough for relative comparison between the two architectures on the
same corpus, not for billing-grade precision. Cost is $0 whenever no LLM
call actually happened (the extractive/fallback generator) — that's a real
finding, not a bug: a deterministic pipeline with no API key genuinely costs
nothing to run.
"""

import math

from rag_core import settings


def estimate_tokens(text):
    """Rough token count for a piece of text (~4 chars/token)."""
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def estimate_cost_usd(input_tokens, output_tokens):
    """Estimated API cost in USD for the given token counts.

    Rates are read from settings (RAG_PRICE_PER_1K_INPUT/OUTPUT) so they can
    be pointed at whatever provider/model is actually configured — the
    defaults are placeholders, not a claim about real Groq pricing.
    """
    cost = (input_tokens / 1000.0) * settings.PRICE_PER_1K_INPUT \
        + (output_tokens / 1000.0) * settings.PRICE_PER_1K_OUTPUT
    return round(cost, 6)


def percentiles(values, ps=(50, 99)):
    """Return {p: value} for each percentile in ps using nearest-rank on the
    sorted list. With very small samples (e.g. 10 runs) p99 collapses toward
    the max — that's expected and worth noting in the write-up, not a bug."""
    if not values:
        return {p: 0.0 for p in ps}
    ordered = sorted(values)
    out = {}
    for p in ps:
        rank = max(1, math.ceil((p / 100.0) * len(ordered)))
        out[p] = ordered[min(rank, len(ordered)) - 1]
    return out
