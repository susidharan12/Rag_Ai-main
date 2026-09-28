"""Week 8 - the 10 documentation queries and their trajectory ground truth.

Reuses week7_agent.race._load_scenarios() for the question text, golden
answer, category, and depends_on_step2 flag rather than re-authoring a
second question set: these are the same 10 real "compare/migrate X between
API versions" scenarios (corpus/dev_docs — GitHub REST API + Swagger
Codegen v2/v3 reference PDFs) week7's race already outcome-scores, so the
Week 8 gap (outcome pass rate - trajectory pass rate) is computed on the
SAME runs, not a different question set that would make the comparison
meaningless.

What Week 8 adds per query is the TRAJECTORY spec: which tool(s) are
*required* (not just "any plausible tool"), the optimal number of
non-finish tool calls, the flexible SET of acceptable tool-call sequences
(order-sensitive, but several alternative orderings/subsets are all
correct - see the assignment's "Flexible Assertions" requirement), and the
version strings that are actually valid for that question (used to catch
a hallucinated version argument, e.g. "v9" or the wrong SDK's version
family, that Pydantic's free-form `str` fields don't reject on their own).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from week7_agent.race import _load_scenarios  # noqa: E402

# The 4 real retrieval/lookup tools that are ever plausible for a
# version-migration/comparison question in this corpus.
RETRIEVAL_TOOLS = frozenset(
    {"search_docs", "get_version_info", "compare_versions", "check_deprecation"}
)

# Tools that exist in rag_core.agent but have no business being called for
# ANY of these 10 migration/comparison questions - they answer a different
# class of question (HTTP error-code lookups, single-parameter default
# lookups). Calling one of these here is a "wrong_tool_choice" failure,
# not a stylistic quibble: it means the agent misread the question.
DISALLOWED_TOOLS = frozenset({"get_error_info", "get_parameter_default"})


def _dependency_spec(valid_versions):
    """Trajectory shape shared by the 4 "step 3 depends on step 2" questions
    (H01/H04/H06/H08 - see week7_agent/race.py's _DEPENDENCY_IDS): the
    golden answer is framed as "old behavior removed/replaced", so
    check_deprecation is a REQUIRED follow-up, not an optional one. Optimal
    path is 2 tool calls: one retrieval call to find the change, then
    check_deprecation to confirm the replacement - never 1 (can't diagnose
    a replacement without first finding what changed) and no need for 3+
    (calling both compare_versions AND get_version_info before
    check_deprecation is redundant, not a second "equally good" path)."""
    return dict(
        required_tools=frozenset({"check_deprecation"}),
        optimal_steps=2,
        valid_versions=valid_versions,
        expected_tool_paths={
            ("search_docs", "check_deprecation"),
            ("get_version_info", "check_deprecation"),
            ("compare_versions", "check_deprecation"),
            ("search_docs", "get_version_info", "check_deprecation"),
            ("search_docs", "compare_versions", "check_deprecation"),
            ("compare_versions", "get_version_info", "check_deprecation"),
            ("get_version_info", "compare_versions", "check_deprecation"),
        },
    )


def _comparison_spec(valid_versions):
    """Trajectory shape for the 6 "compare/migrate" questions that do NOT
    hinge on a removed/replaced fact - no tool is strictly required, but
    the agent must retrieve BOTH versions' docs somehow before answering.
    compare_versions alone is the single most efficient correct path
    (it fetches both versions in one call), which is why optimal_steps=1;
    two separate get_version_info calls or a search_docs pass are also
    legitimate, just less efficient."""
    return dict(
        required_tools=frozenset(),
        optimal_steps=1,
        valid_versions=valid_versions,
        expected_tool_paths={
            ("compare_versions",),
            ("search_docs", "compare_versions"),
            ("compare_versions", "search_docs"),
            ("get_version_info", "get_version_info"),
            ("search_docs", "get_version_info"),
            ("search_docs",),
        },
    )


_GITHUB_VERSIONS = frozenset({"2022-11-28", "2025-06-01"})
# Both "2.x"/"3.x" (the version family label used in these questions) and
# "v2"/"v3" (what the corpus PDFs and get_version_info's sdk_version filter
# actually use, e.g. "Swagger Codegen Reference - v3") are genuinely correct
# identifiers for this corpus - a tool call naming either is grounded, not
# hallucinated, so both must count as valid here or a correct call gets
# wrongly tagged invalid_argument.
_SWAGGER_VERSIONS = frozenset({"2.x", "3.x", "v2", "v3"})

# id -> trajectory spec. IDs and version families match
# week7_agent/golden_sets/gs_hard.json's first 10 non-negative cases
# (see week7_agent/race.py::_DEPENDENCY_IDS for H01/H04/H06/H08).
TRAJECTORY_SPECS = {
    "H01": _dependency_spec(_GITHUB_VERSIONS),   # context param format change
    "H02": _comparison_spec(_SWAGGER_VERSIONS),  # .swagger-codegen-ignore negation
    "H03": _comparison_spec(_SWAGGER_VERSIONS),  # additionalProperties nesting key
    "H04": _dependency_spec(_GITHUB_VERSIONS),   # maintainer_can_modify
    "H05": _comparison_spec(_SWAGGER_VERSIONS),  # Java oneOf + webclient migration
    "H06": _dependency_spec(_GITHUB_VERSIONS),   # make_latest replaces heuristic
    "H07": _comparison_spec(_SWAGGER_VERSIONS),  # Java docs format comparison
    "H08": _dependency_spec(_GITHUB_VERSIONS),   # draft PR auto-merge
    "H09": _comparison_spec(_GITHUB_VERSIONS),   # markdown table wrap_tables
    "H10": _comparison_spec(_SWAGGER_VERSIONS),  # Python asyncio + YAML migration
}


def load_queries(count=10):
    """The 10 scenarios (question/golden_answer/category/id) joined with
    their Week 8 trajectory spec."""
    scenarios = _load_scenarios(count)
    out = []
    for sc in scenarios:
        spec = TRAJECTORY_SPECS[sc["id"]]
        out.append({**sc, **spec})
    return out
