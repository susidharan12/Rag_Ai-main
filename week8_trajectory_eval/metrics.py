"""Week 8 - Trajectory Metrics Engine.

Four telemetry dimensions computed across one full run of the 10-query
suite (a "run" = one call to trajectory_eval.run_suite):

  tool_choice_accuracy   - % of non-finish tool-call steps that picked a
                            tool from this question's plausible vocabulary
                            (i.e. not one of queries.DISALLOWED_TOOLS).
  argument_validity_rate - % of non-finish tool-call steps whose arguments
                            were semantically valid (see taxonomy.py).
  step_efficiency         - mean(actual non-finish steps / optimal steps)
                            across the 10 queries; 1.0 = always optimal,
                            >1.0 = systematically more steps than needed.
  cost_distribution       - p50 and MAX (never a bare mean - a single
                            runaway-loop query should be visible, not
                            averaged away) of est_cost_usd across the 10
                            per-query runs.
"""

from week8_trajectory_eval.queries import DISALLOWED_TOOLS
from week8_trajectory_eval.taxonomy import _is_valid_arg_step


def _non_finish_steps(steps):
    return [s for s in steps if s.get("tool") != "finish"]


def tool_choice_accuracy(records):
    """records: list of {"steps": [...], ...} agent run dicts (already
    joined with their query spec via record["spec"])."""
    total = 0
    valid = 0
    for r in records:
        for s in _non_finish_steps(r["steps"]):
            total += 1
            if s.get("tool") not in DISALLOWED_TOOLS:
                valid += 1
    return (valid / total) if total else 1.0


def argument_validity_rate(records):
    total = 0
    valid = 0
    for r in records:
        spec = r["spec"]
        for s in _non_finish_steps(r["steps"]):
            if s.get("observation", "").startswith("Tool call rejected:"):
                # Already caught and rejected before execution - a schema
                # failure, not a silently-accepted invalid argument. Counted
                # separately (see REPORT.md); excluded from this rate so it
                # isn't double-penalized as both a schema AND an argument
                # failure.
                continue
            total += 1
            if _is_valid_arg_step(s, spec):
                valid += 1
    return (valid / total) if total else 1.0


def step_efficiency(records):
    """Per-query ratio actual/optimal, plus the mean across all 10."""
    per_query = {}
    for r in records:
        actual = len(_non_finish_steps(r["steps"]))
        optimal = r["spec"]["optimal_steps"]
        per_query[r["id"]] = round(actual / optimal, 3) if optimal else float(actual)
    mean = round(sum(per_query.values()) / len(per_query), 3) if per_query else 0.0
    return {"per_query": per_query, "mean": mean}


def cost_distribution(records):
    costs = sorted(r["metrics"]["est_cost_usd"] for r in records)
    if not costs:
        return {"p50": 0.0, "max": 0.0}
    n = len(costs)
    mid = n // 2
    p50 = costs[mid] if n % 2 else round((costs[mid - 1] + costs[mid]) / 2, 6)
    return {"p50": round(p50, 6), "max": round(costs[-1], 6)}


def latency_distribution(records):
    """Not one of the 4 required dimensions, but reported alongside cost
    for context (same p50/max framing) since latency circuit breakers are
    part of Week 7/8's safety-boundary story."""
    lat = sorted(r["metrics"]["latency_ms"] for r in records)
    if not lat:
        return {"p50": 0.0, "max": 0.0}
    n = len(lat)
    mid = n // 2
    p50 = lat[mid] if n % 2 else round((lat[mid - 1] + lat[mid]) / 2, 1)
    return {"p50": round(p50, 1), "max": round(lat[-1], 1)}


def summarize(records):
    return {
        "tool_choice_accuracy": round(tool_choice_accuracy(records), 3),
        "argument_validity_rate": round(argument_validity_rate(records), 3),
        "step_efficiency": step_efficiency(records),
        "cost_distribution_usd": cost_distribution(records),
        "latency_distribution_ms": latency_distribution(records),
    }
