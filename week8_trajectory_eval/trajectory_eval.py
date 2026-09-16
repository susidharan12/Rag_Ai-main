"""Week 8 - Trajectory Eval Suite.

Runs the real ReAct agent (rag_core.agent.run_agent) over the same 10 real
migration/comparison scenarios week7_agent/race.py outcome-scores, twice:

  "before"  enforce_deprecation_check=False (today's shipped default)
  "after"   enforce_deprecation_check=True  (the one mitigation - see
            rag_core/agent.py::run_agent docstring)

Note: an earlier hypothesis (recover a step whose LLM output fails to
parse via the deterministic fallback planner, instead of aborting with
stopped_by="parse_error") was implemented and measured first. It produced
a genuine null result - see REPORT.md "What was tried first, and why it
didn't move the needle" - because parse failures never actually occurred
in that live run (parse_recoveries==0 in every query, both conditions).
That code was reverted; THIS file measures the fix that replaced it.

For every run it records BOTH scores:
  outcome pass/fail    - week7_agent.race._score_answer (golden-token
                         overlap >= 60%), unchanged from Week 7.
  trajectory pass/fail - did the run actually execute a valid tool path
                         for this question (queries.TRAJECTORY_SPECS),
                         via taxonomy.classify/trajectory_passed.

Then computes:
  - the Trajectory Metrics Engine's 4 dimensions (metrics.py)
  - Gap = outcome_pass_rate - trajectory_pass_rate (on the "before" run -
    the shipped, unmitigated system)
  - one concrete "right answer, wrong path" trace (outcome PASS +
    trajectory FAIL) from the "before" run
  - a before/after regression matrix, one row per taxonomy.FAILURE_MODES

Usage:
    python -m week8_trajectory_eval.trajectory_eval
    #  -> week8_trajectory_eval/traces_before.json
    #  -> week8_trajectory_eval/traces_after.json
    #  -> week8_trajectory_eval/report.json
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Reuses week7's isolated-index builder and outcome scorer verbatim - same
# corpus, same scoring rule, so Week 8's gap is measured against the exact
# same "correct answer" bar Week 7 shipped, not a redefined one.
from week7_agent.race import _ensure_index_built, _score_answer  # noqa: E402

from rag_core.agent import run_agent  # noqa: E402
from week8_trajectory_eval import metrics as metrics_mod  # noqa: E402
from week8_trajectory_eval import taxonomy  # noqa: E402
from week8_trajectory_eval.queries import load_queries  # noqa: E402

MAX_STEPS = 4       # matches week7_agent/race.py's rate-limit-tuned cap
TIME_BUDGET = 30


def run_suite(enforce_deprecation_check, store, queries):
    """Run all 10 queries once through run_agent; return one record per
    query with outcome + trajectory scoring attached."""
    records = []
    for q in queries:
        t0 = time.perf_counter()
        agent_res = run_agent(
            q["question"], store,
            max_steps=MAX_STEPS, time_budget=TIME_BUDGET,
            enforce_deprecation_check=enforce_deprecation_check,
        )
        wall_ms = round((time.perf_counter() - t0) * 1000, 1)

        outcome_score, outcome_pass = _score_answer(agent_res["answer"], q)

        tags = taxonomy.classify(
            agent_res["steps"], q, agent_res["metrics"]["stopped_by"]
        )
        traj_pass = taxonomy.trajectory_passed(tags)

        tool_path = tuple(
            s["tool"] for s in agent_res["steps"] if s["tool"] != "finish"
        )
        # dedupe consecutive/overall while preserving first-seen order, to
        # compare against expected_tool_paths (which are unique-tool
        # sequences, not a literal call-by-call log).
        seen = []
        for t in tool_path:
            if t not in seen:
                seen.append(t)
        tool_path_unique = tuple(seen)

        records.append({
            "id": q["id"],
            "question": q["question"],
            "category": q["category"],
            "spec": q,
            "answer": agent_res["answer"],
            "steps": agent_res["steps"],
            "metrics": agent_res["metrics"],
            "wall_clock_ms": wall_ms,
            "outcome_score": round(outcome_score, 3),
            "outcome_pass": outcome_pass,
            "failure_tags": sorted(tags),
            "trajectory_pass": traj_pass,
            "tool_path": tool_path_unique,
            "path_in_expected_set": tool_path_unique in q["expected_tool_paths"],
        })
    return records


def _pass_rate(records, key):
    return round(sum(1 for r in records if r[key]) / len(records), 3) if records else 0.0


def _find_false_positive(records):
    """First record where outcome PASSED but trajectory FAILED - a
    right-answer-wrong-path case. None if the "before" run happens to have
    none (report that honestly too)."""
    for r in records:
        if r["outcome_pass"] and not r["trajectory_pass"]:
            return r
    return None


def _regression_matrix(before_records, after_records):
    def counts(records):
        c = {m: 0 for m in taxonomy.FAILURE_MODES}
        for r in records:
            for tag in r["failure_tags"]:
                c[tag] += 1
        return c

    before_counts = counts(before_records)
    after_counts = counts(after_records)
    rows = []
    for mode in taxonomy.FAILURE_MODES:
        b, a = before_counts[mode], after_counts[mode]
        rows.append({
            "failure_mode": mode,
            "before": b,
            "after": a,
            "delta": a - b,
            "regressed": a > b,
        })
    return rows


def _serializable(records):
    """Drop nothing, just make tuples/sets JSON-safe and trim the query
    spec down to its JSON-safe fields (it carries frozensets/sets)."""
    out = []
    for r in records:
        rec = dict(r)
        rec["tool_path"] = list(rec["tool_path"])
        spec = rec["spec"]
        rec["spec"] = {
            "id": spec["id"], "category": spec["category"],
            "required_tools": sorted(spec["required_tools"]),
            "optimal_steps": spec["optimal_steps"],
            "valid_versions": sorted(spec["valid_versions"]),
            "expected_tool_paths": sorted(list(p) for p in spec["expected_tool_paths"]),
            "depends_on_step2": spec.get("depends_on_step2", False),
        }
        out.append(rec)
    return out


def main():
    queries = load_queries()
    store = _ensure_index_built()

    print(f"\n{'='*60}\n  WEEK 8 TRAJECTORY EVAL — before (enforce_deprecation_check=False)\n{'='*60}")
    before = run_suite(False, store, queries)
    for r in before:
        print(f"  {r['id']}: outcome={'PASS' if r['outcome_pass'] else 'FAIL'} "
              f"traj={'PASS' if r['trajectory_pass'] else 'FAIL'} "
              f"tags={r['failure_tags']} path={r['tool_path']}")

    print(f"\n{'='*60}\n  WEEK 8 TRAJECTORY EVAL — after (enforce_deprecation_check=True)\n{'='*60}")
    after = run_suite(True, store, queries)
    for r in after:
        print(f"  {r['id']}: outcome={'PASS' if r['outcome_pass'] else 'FAIL'} "
              f"traj={'PASS' if r['trajectory_pass'] else 'FAIL'} "
              f"tags={r['failure_tags']} path={r['tool_path']}")

    before_outcome_pr = _pass_rate(before, "outcome_pass")
    before_traj_pr = _pass_rate(before, "trajectory_pass")
    after_outcome_pr = _pass_rate(after, "outcome_pass")
    after_traj_pr = _pass_rate(after, "trajectory_pass")
    gap_before = round(before_outcome_pr - before_traj_pr, 3)
    gap_after = round(after_outcome_pr - after_traj_pr, 3)

    false_positive = _find_false_positive(before)
    regression = _regression_matrix(before, after)

    before_metrics = metrics_mod.summarize(before)
    after_metrics = metrics_mod.summarize(after)

    price_paid = {
        "added_p50_latency_ms": round(
            after_metrics["latency_distribution_ms"]["p50"]
            - before_metrics["latency_distribution_ms"]["p50"], 1),
        "added_max_latency_ms": round(
            after_metrics["latency_distribution_ms"]["max"]
            - before_metrics["latency_distribution_ms"]["max"], 1),
        "added_p50_cost_usd": round(
            after_metrics["cost_distribution_usd"]["p50"]
            - before_metrics["cost_distribution_usd"]["p50"], 6),
        "added_max_cost_usd": round(
            after_metrics["cost_distribution_usd"]["max"]
            - before_metrics["cost_distribution_usd"]["max"], 6),
        "total_est_tokens_before": sum(r["metrics"]["est_tokens"] for r in before),
        "total_est_tokens_after": sum(r["metrics"]["est_tokens"] for r in after),
    }

    target_mode = "missing_required_tool"
    target_before = next(r for r in regression if r["failure_mode"] == target_mode)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_queries": len(queries),
        "before": {
            "outcome_pass_rate": before_outcome_pr,
            "trajectory_pass_rate": before_traj_pr,
            "gap": gap_before,
            "metrics": before_metrics,
        },
        "after": {
            "outcome_pass_rate": after_outcome_pr,
            "trajectory_pass_rate": after_traj_pr,
            "gap": gap_after,
            "metrics": after_metrics,
        },
        "false_positive_trace": {
            "id": false_positive["id"],
            "question": false_positive["question"],
            "outcome_score": false_positive["outcome_score"],
            "failure_tags": false_positive["failure_tags"],
            "tool_path": list(false_positive["tool_path"]),
            "stopped_by": false_positive["metrics"]["stopped_by"],
            "answer": false_positive["answer"],
            "steps": false_positive["steps"],
        } if false_positive else None,
        "mitigation": {
            "target_failure_mode": target_mode,
            "fix": "rag_core.agent.run_agent(enforce_deprecation_check=True) - "
                   "a `finish` call is held back once when the retrieved "
                   "context already shows a change/replacement for a "
                   "subject+version this question names but "
                   "check_deprecation was never called (see "
                   "_needs_deprecation_check); the agent gets one more "
                   "observation telling it to call check_deprecation before "
                   "finishing, bounded to fire at most once per run.",
            "before_count": target_before["before"],
            "after_count": target_before["after"],
            "delta": target_before["delta"],
            "price_paid": price_paid,
        },
        "regression_matrix": regression,
    }

    with open(os.path.join(HERE, "traces_before.json"), "w", encoding="utf-8") as f:
        json.dump(_serializable(before), f, indent=2, ensure_ascii=False, default=str)
    with open(os.path.join(HERE, "traces_after.json"), "w", encoding="utf-8") as f:
        json.dump(_serializable(after), f, indent=2, ensure_ascii=False, default=str)
    with open(os.path.join(HERE, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'='*60}\n  RESULTS\n{'='*60}")
    print(f"  Before: outcome_pass_rate={before_outcome_pr:.0%} "
          f"trajectory_pass_rate={before_traj_pr:.0%} gap={gap_before:+.3f}")
    print(f"  After:  outcome_pass_rate={after_outcome_pr:.0%} "
          f"trajectory_pass_rate={after_traj_pr:.0%} gap={gap_after:+.3f}")
    print(f"  Mitigation target '{target_mode}': "
          f"{target_before['before']} -> {target_before['after']} "
          f"(delta {target_before['delta']:+d})")
    print(f"  Price paid: {json.dumps(price_paid)}")
    print(f"  Regression matrix: {json.dumps(regression, indent=2)}")
    print(f"\n  Wrote traces_before.json, traces_after.json, report.json in {HERE}")


if __name__ == "__main__":
    main()
