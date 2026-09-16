"""Week 8 - Trajectory Test Suite (pytest).

10 cases, one per documentation query, each asserting the agent's actual
tool-call trajectory in code. Assertions are made against a SET of
acceptable tool paths (queries.TRAJECTORY_SPECS[...]["expected_tool_paths"])
rather than one rigid sequence - a question like "compare X between v2 and
v3" is answered correctly whether the agent calls compare_versions alone,
or search_docs then compare_versions, or two get_version_info calls; all
are asserted as valid, not just whichever one the agent happened to take.

Reads from the CACHED trace file (traces_before.json, i.e. the shipped/
unmitigated agent) that `python -m week8_trajectory_eval.trajectory_eval`
produces, rather than calling a real LLM per test run - keeps the suite
fast, deterministic, and runnable in CI without an API key. Regenerate the
cache (and re-run this suite against it) any time the corpus, prompt, or
agent logic changes.

Run: python -m pytest week8_trajectory_eval/test_trajectory_eval.py -v
"""

import json
import os

import pytest

from week8_trajectory_eval.queries import TRAJECTORY_SPECS
from week8_trajectory_eval.taxonomy import trajectory_passed

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE_PATH = os.path.join(HERE, "traces_before.json")


def _load_traces():
    if not os.path.exists(TRACE_PATH):
        pytest.skip(
            f"{TRACE_PATH} not found - run "
            "`python -m week8_trajectory_eval.trajectory_eval` first to "
            "generate real agent traces to assert against."
        )
    with open(TRACE_PATH, "r", encoding="utf-8") as f:
        return {r["id"]: r for r in json.load(f)}


_TRACES = None


def _traces():
    global _TRACES
    if _TRACES is None:
        _TRACES = _load_traces()
    return _TRACES


@pytest.mark.parametrize("query_id", sorted(TRAJECTORY_SPECS.keys()))
def test_tool_path_in_expected_set(query_id):
    """The actual (deduped, ordered) non-finish tool sequence must be one
    of this query's pre-registered legitimate paths - a flexible SET
    membership check, not an exact single-sequence match."""
    traces = _traces()
    assert query_id in traces, f"no cached trace for {query_id}"
    record = traces[query_id]
    spec = TRAJECTORY_SPECS[query_id]

    actual_path = tuple(record["tool_path"])
    expected_paths = spec["expected_tool_paths"]

    assert actual_path in expected_paths, (
        f"{query_id}: tool path {actual_path} is not one of the "
        f"{len(expected_paths)} accepted paths for this query: "
        f"{sorted(expected_paths)}"
    )


@pytest.mark.parametrize("query_id", sorted(TRAJECTORY_SPECS.keys()))
def test_required_tools_present(query_id):
    """Every tool this query REQUIRES (e.g. check_deprecation on the 4
    dependency questions) must actually appear in the trajectory - this is
    the assertion the false-positive trace in REPORT.md fails."""
    traces = _traces()
    record = traces[query_id]
    spec = TRAJECTORY_SPECS[query_id]

    actual_tools = set(record["tool_path"])
    missing = spec["required_tools"] - actual_tools
    assert not missing, (
        f"{query_id}: required tool(s) {sorted(missing)} never called "
        f"(actual path: {record['tool_path']}, failure_tags: "
        f"{record['failure_tags']})"
    )


@pytest.mark.parametrize("query_id", sorted(TRAJECTORY_SPECS.keys()))
def test_no_tool_bypass(query_id):
    """The agent must call at least one real retrieval tool before
    finishing - never answer purely from memory."""
    traces = _traces()
    record = traces[query_id]
    assert len(record["tool_path"]) >= 1, (
        f"{query_id}: agent answered with zero tool calls "
        f"(answer={record['answer']!r})"
    )


@pytest.mark.parametrize("query_id", sorted(TRAJECTORY_SPECS.keys()))
def test_trajectory_pass_matches_taxonomy(query_id):
    """Sanity check that the cached trajectory_pass flag agrees with
    taxonomy.trajectory_passed() re-applied to the cached failure_tags -
    guards against the cache and the classifier drifting apart."""
    traces = _traces()
    record = traces[query_id]
    assert record["trajectory_pass"] == trajectory_passed(set(record["failure_tags"]))
