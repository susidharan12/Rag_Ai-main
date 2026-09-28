"""Week 8 - failure-mode taxonomy for agent trajectories.

Each mode below is checked independently against one agent run + its
query spec (week8_trajectory_eval.queries.TRAJECTORY_SPECS); a single run
can carry more than one tag. `classify` is the single source of truth used
by both trajectory_eval.py (the metrics/regression run) and
test_trajectory_eval.py (the assertion suite), so the two never drift.

Modes:

  no_tool_before_finish
      The agent answered without ever calling a real retrieval tool - the
      "recites a plausible answer from pre-trained memory instead of
      executing the spec-lookup tool" failure this assignment names
      explicitly. Always a trajectory failure.

  missing_required_tool
      A query-specific mandatory follow-up tool (here: check_deprecation
      on the 4 "step 3 depends on step 2" questions) never ran. This is
      the mode the real, historical H01 trace demonstrates (see REPORT.md)
      and the one the mitigation in rag_core.agent targets. Trajectory
      failure.

  wrong_tool_choice
      A tool outside this question's plausible vocabulary was called
      (queries.DISALLOWED_TOOLS - error-code / parameter-default lookups
      on a version-migration question). Trajectory failure.

  invalid_argument
      A tool call's argument was semantically invalid for this question -
      not a Pydantic schema violation (those are rejected before
      execution and never reach this classifier), but a *hallucinated*
      value a schema can't catch: a version string that isn't one of the
      two versions this question is actually about, or an empty/blank
      query string. Trajectory failure.

  redundant_repeat
      The exact same (tool, args) pair was called more than once in one
      run - wasted steps that hurt step efficiency without gathering any
      new evidence. Not itself a trajectory failure (it doesn't make the
      answer wrong), but tracked because it eats into the step budget.

  premature_stop_parse_error
      The run ended with stopped_by == "parse_error" - the LLM's step
      output failed to parse as JSON and (pre-mitigation) the loop
      aborted right there, however few tools had run. Not itself a
      trajectory failure (the *other* modes already capture whether that
      early stop actually cost the run a required tool call) - tracked
      separately so the regression matrix can show the mitigation's
      direct effect on ITS target mode.
"""

FAILURE_MODES = (
    "no_tool_before_finish",
    "missing_required_tool",
    "wrong_tool_choice",
    "invalid_argument",
    "redundant_repeat",
    "premature_stop_parse_error",
)

# Modes that, if present, make the trajectory itself a FAIL (as opposed to
# premature_stop_parse_error/redundant_repeat, which are recorded for the
# regression matrix but don't by themselves fail an otherwise-clean run).
DISQUALIFYING_MODES = frozenset(
    {"no_tool_before_finish", "missing_required_tool", "wrong_tool_choice",
     "invalid_argument"}
)


def _ordered_unique_tools(steps):
    """Non-finish tool names, in first-seen order, deduped."""
    seen = []
    for s in steps:
        t = s.get("tool")
        if t and t != "finish" and t not in seen:
            seen.append(t)
    return tuple(seen)


def _is_valid_arg_step(step, spec):
    """True if this single tool-call step's arguments are semantically
    valid for the query spec. Only checks the fields that can actually
    carry a hallucinated/invalid value in this tool set - see module
    docstring."""
    tool = step.get("tool")
    args = step.get("args") or {}
    valid_versions = spec.get("valid_versions") or set()

    if tool == "check_deprecation":
        version = args.get("api_version", "")
        version = getattr(version, "value", version)
        return version in valid_versions
    if tool == "get_version_info":
        version = args.get("version", "")
        # A blank/placeholder version is as invalid as a wrong one.
        if not version:
            return False
        return version in valid_versions
    if tool in ("search_docs", "compare_versions", "get_error_info",
                "get_parameter_default"):
        return bool((args.get("query") or "").strip())
    return True


def classify(run_steps, spec, stopped_by):
    """Return the set of failure-mode tags that apply to this run.

    run_steps: the agent's `steps` list (list of {tool, args, observation}).
    spec: this query's TRAJECTORY_SPECS entry.
    stopped_by: agent metrics["stopped_by"].
    """
    tags = set()
    tool_only_steps = [s for s in run_steps if s.get("tool") != "finish"]
    tools_used = _ordered_unique_tools(run_steps)

    if not tools_used:
        tags.add("no_tool_before_finish")

    if not spec["required_tools"].issubset(set(tools_used)):
        tags.add("missing_required_tool")

    from week8_trajectory_eval.queries import DISALLOWED_TOOLS
    if set(tools_used) & DISALLOWED_TOOLS:
        tags.add("wrong_tool_choice")

    for s in tool_only_steps:
        if s.get("observation", "").startswith("Tool call rejected:"):
            continue  # schema already rejected it; not counted twice here
        if not _is_valid_arg_step(s, spec):
            tags.add("invalid_argument")
            break

    seen_calls = set()
    for s in tool_only_steps:
        key = (s.get("tool"), tuple(sorted((s.get("args") or {}).items())))
        if key in seen_calls:
            tags.add("redundant_repeat")
        seen_calls.add(key)

    if stopped_by == "parse_error":
        tags.add("premature_stop_parse_error")

    return tags


def trajectory_passed(tags):
    """A run's trajectory is correct iff none of the disqualifying modes
    fired - premature_stop_parse_error/redundant_repeat alone don't fail
    it (they're recorded for the regression matrix, not the pass/fail
    gate)."""
    return not (tags & DISQUALIFYING_MODES)
