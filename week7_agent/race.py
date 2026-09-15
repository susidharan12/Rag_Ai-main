"""Week 7 · Race — Agent vs Fixed Workflow comparison.

Runs both approaches on the same 10 real migration/comparison scenarios
(drawn from week7_agent/golden_sets/gs_hard.json, scored against the golden
answers) and compares:
  - Pass/success rate (key facts from the golden answer present in the
    produced answer; refusal-correctness for negative cases)
  - Speed (p50/p99/avg latency in ms)
  - Cost (estimated tokens + estimated $ — genuinely $0 when no LLM call
    happened, i.e. the extractive/fallback path)

Usage:
    python -m week7_agent.race                # run the full 10-scenario race
    python -m week7_agent.race --quick        # 3-scenario subset
"""

import csv
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

# Use an isolated index under week7_agent/.race_index/ so the race runs
# against the real dev-docs corpus without polluting the live app's data/index/.
RACE_INDEX_DIR = os.path.join(HERE, ".race_index")
os.environ["RAG_DATA_DIR"] = RACE_INDEX_DIR

from rag_core.agent import run_agent
from rag_core.store import DocStore, get_embedding_model
from rag_core.telemetry import percentiles
from rag_core.workflow import run_workflow

DEV_DOCS_DIR = os.path.join(REPO_ROOT, "corpus", "dev_docs")
GOLDEN_SETS_DIR = os.path.join(HERE, "golden_sets")
SCENARIO_COUNT = 10


def _ensure_index_built():
    """Build (or reuse) the isolated index from the real developer-doc PDFs."""
    store = DocStore()
    store.ensure_loaded()
    if store.stats()["documents"] == 0:
        for path in sorted(glob.glob(os.path.join(DEV_DOCS_DIR, "*.pdf"))):
            with open(path, "rb") as f:
                store.add_document(path, f.read())

    # Warm up the lazily-loaded embedding model *before* timing starts —
    # otherwise the first scenario eats a one-time ~30s model-download/load
    # cost that has nothing to do with agent-vs-workflow latency and wrecks
    # avg/p99 for whichever system happens to run first.
    get_embedding_model()
    store.search("warmup", top_k=1)
    return store


# Task Set E requires >= 3 of the 10 race questions where the correct
# answer depends on a chained lookup: step 2 (get_version_info) surfaces
# that a specific parameter/endpoint's behavior changed at the target
# version, and step 3 (check_deprecation) must then be consulted for what
# replaced it — you cannot answer correctly from step 1's raw search alone.
# These 4 IDs (out of the first 10 non-negative gs_hard.json cases) are the
# ones whose golden answer is explicitly framed as "old behavior removed /
# replaced by new behavior", not just "a new option was added":
#   H04 - maintainer_can_modify: could only be set via a follow-up PATCH in
#         2022-11-28; 2025-06-01 replaces that two-step flow with a direct
#         create-time field.
#   H06 - make_latest: replaces an undocumented internal heuristic outright
#         (the golden answer uses the word "replace").
#   H08 - draft-PR auto-merge: the 2022-11-28 restriction (must leave draft
#         state first) is lifted/replaced in 2025-06-01.
#   H01 - the `context` parameter's plain-string format in 2022-11-28 is
#         replaced by a structured owner/repo object in 2025-06-01.
_DEPENDENCY_IDS = {"H01", "H04", "H06", "H08"}


def _load_scenarios(count=SCENARIO_COUNT):
    """The 10 "migration scenario" test questions, sourced from the real
    golden set (gs_hard.json) rather than hand-authored — these are literally
    "compare/migrate X between API versions" and "migrate this Swagger v2
    config to v3" questions. Negative (refusal-expected) cases are skipped
    here since the assignment asks for migration *scenarios*."""
    path = os.path.join(GOLDEN_SETS_DIR, "gs_hard.json")
    with open(path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    scenarios = []
    for case in cases:
        meta = case.get("metadata", {})
        if meta.get("is_negative_case"):
            continue
        sid = f"H{case['id']}"
        scenarios.append({
            "id": sid,
            "question": case["question"],
            "category": meta.get("tool_context", "general"),
            "golden_answer": case["answer"],
            "is_negative": False,
            "depends_on_step2": sid in _DEPENDENCY_IDS,
        })
        if len(scenarios) >= count:
            break
    return scenarios


QUICK_COUNT = 3

# ---------------------------------------------------------------------------
# Scoring — golden-answer-derived, not hand-labeled per question.
# ---------------------------------------------------------------------------

#   (?<!\w)'...'(?!\w)  -- a lookbehind/lookahead guards the single-quote
#   form against possessives/contractions ("repository's") being mistaken
#   for an opening quote: without it, the apostrophe in "repository's"
#   pairs with the NEXT unrelated quote in the sentence and swallows
#   everything between them as one garbage "quoted" token (a real bug this
#   fixes, found while auditing H06's golden answer — see week7_agent
#   README caveats). Double quotes/backticks don't have this problem.
_QUOTED_RE = re.compile(
    r"(?<!\w)'([^']{2,80})'(?!\w)|\"([^\"]{2,80})\"|`([^`]{2,80})`"
)
_NUM_RE = re.compile(r"\b\d{2,4}(?:-\d{2}-\d{2})?\b")
# Fallback fact-extractor for golden answers with no quoted/numeric facts at
# all (e.g. H02's ".swagger-codegen-ignore" negation syntax is written as
# `!pattern` / `!docs/keep-this.md`, never in quotes) — without this, such
# a question can never pass regardless of answer quality, which is a
# scoring dead end, not a reflection of either system's real quality.
_BANG_RE = re.compile(r"!\S{2,40}")
# An inline "(Key: value)" annotation next to an "e.g." is an illustrative
# example value, not a fact the answer is required to restate verbatim.
_ILLUSTRATIVE_EXAMPLE_RE = re.compile(r"^\([^()]*:[^()]*\)$")
_PASS_THRESHOLD = 0.6

_REFUSAL_MARKERS = (
    "could not find", "not provided in context", "does not contain",
    "does not mention", "no relevant", "not contain", "no information",
)


def _extract_key_tokens(golden_answer):
    """Pull the load-bearing facts (quoted values, code flags, numbers/dates)
    out of a golden answer, so scoring needs no manual per-question labels.

    Skips punctuation-only placeholders and illustrative "(Key: value)"
    example annotations (a literal default-value example isn't itself a
    fact the generated answer must restate verbatim)."""
    tokens = set()
    for m in _QUOTED_RE.finditer(golden_answer):
        for g in m.groups():
            if not g:
                continue
            if not re.search(r"[a-z0-9]", g, re.IGNORECASE):
                continue
            if _ILLUSTRATIVE_EXAMPLE_RE.match(g.strip()):
                continue
            tokens.add(g.strip().lower())
    for m in _NUM_RE.finditer(golden_answer):
        tokens.add(m.group().lower())
    if not tokens:
        for m in _BANG_RE.finditer(golden_answer):
            tokens.add(m.group().rstrip(".,)'\"").lower())
    return tokens


def _looks_like_refusal(answer):
    if not answer:
        return True
    low = answer.lower()
    return any(marker in low for marker in _REFUSAL_MARKERS)


def _score_answer(answer, scenario):
    """Return (relevance_score 0..1, passed bool)."""
    if scenario.get("is_negative"):
        passed = _looks_like_refusal(answer)
        return (1.0 if passed else 0.0), passed

    tokens = _extract_key_tokens(scenario["golden_answer"])
    if not tokens:
        return 0.0, False
    low = (answer or "").lower()
    hits = sum(1 for t in tokens if t in low)
    score = hits / len(tokens)
    return score, score >= _PASS_THRESHOLD


def _question_winner(a_pass, a_score, w_pass, w_score):
    """Decide the per-question winner on ANSWER QUALITY ONLY — pass/fail,
    then how correct. Returns (winner, reason) where winner is "agent" |
    "workflow" | "tie".

    Deliberately does NOT fall through to tokens/latency as a tie-break:
    on this corpus, both systems retrieve overlapping context and answer
    through the same generator, so most questions land on an *identical*
    pass/fail + score. Cost/speed differences on those questions are real
    (the workflow always runs a fixed 3-tool sequence; the agent's plan
    skips steps it doesn't need) but they are a structural property of the
    two architectures, not evidence one produced a better answer to THIS
    question — reporting cheaper-therefore-"winner" on every tied question
    would manufacture a false sweep (see the aggregate speed/cost/quality
    winners below, which is where that comparison belongs)."""
    if a_pass != w_pass:
        return ("agent" if a_pass else "workflow"), "pass/fail"
    if abs(a_score - w_score) > 1e-9:
        return ("agent" if a_score > w_score else "workflow"), "relevance score"
    return "tie", "identical pass/fail and relevance score"


def run_race(scenarios=None, store=None):
    """Run the full race and return structured results."""
    if scenarios is None:
        scenarios = _load_scenarios()
    if store is None:
        store = _ensure_index_built()

    agent_results = []
    workflow_results = []

    print(f"\n{'='*60}")
    print(f"  WEEK 7 RACE: Agent vs Fixed Workflow")
    print(f"  Corpus: real developer docs (GitHub REST API + Swagger Codegen v2/v3)")
    print(f"  Scenarios: {len(scenarios)}")
    print(f"{'='*60}\n")

    for i, sc in enumerate(scenarios, 1):
        dep_tag = " [step3 depends on step2]" if sc.get("depends_on_step2") else ""
        print(f"[{i}/{len(scenarios)}] {sc['question']}{dep_tag}")
        print(f"  Category: {sc['category']}")

        # --- Run Agent ---
        print("  Running agent...", end=" ", flush=True)
        # max_steps=4: enough for the full search_docs -> get_version_info/
        # compare_versions -> check_deprecation -> finish chain, capped
        # tighter than the general-purpose default (5) specifically to keep
        # each question's total LLM token usage under a free-tier Groq
        # key's tokens-per-minute budget (observed: 8000 TPM) across a
        # 10-question race — see rag_core/agent.py::_call_llm for the
        # matching per-call max_tokens reduction.
        agent_res = run_agent(sc["question"], store, max_steps=4, time_budget=30)
        a_score, a_pass = _score_answer(agent_res["answer"], sc)
        agent_res["relevance_score"] = a_score
        agent_res["passed"] = a_pass
        agent_res["question_id"] = sc["id"]
        agent_res["category"] = sc["category"]
        agent_res["depends_on_step2"] = sc.get("depends_on_step2", False)
        agent_results.append(agent_res)
        print(f"{agent_res['metrics']['latency_ms']:.0f}ms, "
              f"{agent_res['metrics']['steps_taken']} steps, "
              f"score={a_score:.2f}, {'PASS' if a_pass else 'FAIL'}")

        # --- Run Workflow ---
        print("  Running workflow...", end=" ", flush=True)
        wf_res = run_workflow(sc["question"], store)
        w_score, w_pass = _score_answer(wf_res["answer"], sc)
        wf_res["relevance_score"] = w_score
        wf_res["passed"] = w_pass
        wf_res["question_id"] = sc["id"]
        wf_res["category"] = sc["category"]
        wf_res["depends_on_step2"] = sc.get("depends_on_step2", False)
        workflow_results.append(wf_res)
        print(f"{wf_res['metrics']['latency_ms']:.0f}ms, "
              f"score={w_score:.2f}, {'PASS' if w_pass else 'FAIL'}")

        # --- Decide this question's overall winner ---
        winner, reason = _question_winner(a_pass, a_score, w_pass, w_score)
        agent_res["question_winner"] = wf_res["question_winner"] = winner
        agent_res["question_winner_reason"] = wf_res["question_winner_reason"] = reason
        print(f"  Winner: {winner} ({reason})")

        print()

    # --- Aggregate ---
    agent_latencies = [r["metrics"]["latency_ms"] for r in agent_results]
    wf_latencies = [r["metrics"]["latency_ms"] for r in workflow_results]
    agent_p = percentiles(agent_latencies)
    wf_p = percentiles(wf_latencies)

    agent_avg_time = sum(agent_latencies) / len(agent_latencies)
    wf_avg_time = sum(wf_latencies) / len(wf_latencies)
    agent_avg_score = sum(r["relevance_score"] for r in agent_results) / len(agent_results)
    wf_avg_score = sum(r["relevance_score"] for r in workflow_results) / len(workflow_results)
    agent_pass_rate = sum(r["passed"] for r in agent_results) / len(agent_results)
    wf_pass_rate = sum(r["passed"] for r in workflow_results) / len(workflow_results)
    agent_total_calls = sum(r["metrics"]["api_calls"] for r in agent_results)
    wf_total_calls = sum(r["metrics"]["api_calls"] for r in workflow_results)
    agent_avg_steps = sum(r["metrics"]["steps_taken"] for r in agent_results) / len(agent_results)
    wf_avg_steps = sum(len(r["steps"]) for r in workflow_results) / len(workflow_results)
    agent_total_tokens = sum(r["metrics"]["est_tokens"] for r in agent_results)
    wf_total_tokens = sum(r["metrics"]["est_tokens"] for r in workflow_results)
    agent_total_cost = sum(r["metrics"]["est_cost_usd"] for r in agent_results)
    wf_total_cost = sum(r["metrics"]["est_cost_usd"] for r in workflow_results)

    speed_winner = "workflow" if wf_avg_time < agent_avg_time else "agent"
    # Tie-break on est_tokens, not api_calls: api_calls counts different
    # things for each system (agent: tool calls, local & free; workflow:
    # billable LLM calls) so it isn't a fair tie-break — est_tokens *is*
    # computed the same way for both (see rag_core/workflow.py) and is what
    # cost is actually derived from.
    cost_winner = ("workflow" if wf_total_cost < agent_total_cost
                    else "agent" if agent_total_cost < wf_total_cost
                    else ("workflow" if wf_total_tokens <= agent_total_tokens else "agent"))
    quality_winner = "workflow" if wf_pass_rate >= agent_pass_rate else "agent"

    question_wins = {"agent": 0, "workflow": 0, "tie": 0}
    for r in agent_results:
        question_wins[r["question_winner"]] += 1
    overall_winner = "tie"
    if question_wins["agent"] != question_wins["workflow"]:
        overall_winner = "agent" if question_wins["agent"] > question_wins["workflow"] else "workflow"

    dependency_ids = [r["question_id"] for r in agent_results if r["depends_on_step2"]]
    agent_used_check_deprecation = sum(
        1 for r in agent_results
        if r["depends_on_step2"] and "check_deprecation" in r["metrics"]["tools_used"]
    )

    summary = {
        "total_questions": len(scenarios),
        "dependency_questions": {
            "count": len(dependency_ids),
            "ids": dependency_ids,
            "agent_actually_called_check_deprecation": agent_used_check_deprecation,
        },
        "agent": {
            "avg_latency_ms": round(agent_avg_time, 1),
            "p50_latency_ms": round(agent_p[50], 1),
            "p99_latency_ms": round(agent_p[99], 1),
            "pass_rate": round(agent_pass_rate, 3),
            "avg_relevance_score": round(agent_avg_score, 3),
            "total_api_calls": agent_total_calls,
            "avg_steps": round(agent_avg_steps, 1),
            "total_est_tokens": agent_total_tokens,
            "total_est_cost_usd": round(agent_total_cost, 6),
        },
        "workflow": {
            "avg_latency_ms": round(wf_avg_time, 1),
            "p50_latency_ms": round(wf_p[50], 1),
            "p99_latency_ms": round(wf_p[99], 1),
            "pass_rate": round(wf_pass_rate, 3),
            "avg_relevance_score": round(wf_avg_score, 3),
            "total_api_calls": wf_total_calls,
            "avg_steps": round(wf_avg_steps, 1),  # fixed: search_docs, get_version_info, check_deprecation, generate
            "total_est_tokens": wf_total_tokens,
            "total_est_cost_usd": round(wf_total_cost, 6),
        },
        "winner": {
            "speed": speed_winner,
            "cost": cost_winner,
            "quality": quality_winner,
            "overall": overall_winner,
        },
        "question_wins": question_wins,
    }

    # --- Build the verdict paragraph (data-driven, not hard-coded to
    # whichever system happened to win a prior run) ---
    faster_name = "workflow" if wf_avg_time <= agent_avg_time else "agent"
    faster_time = wf_avg_time if faster_name == "workflow" else agent_avg_time
    slower_time = agent_avg_time if faster_name == "workflow" else wf_avg_time
    speed_ratio = (slower_time / faster_time) if faster_time > 0 else 1.0

    dep_ids_str = ", ".join(dependency_ids)
    n_dep = len(dependency_ids)
    # Cheaper/faster labels are computed from THIS run's numbers, not
    # asserted in one direction — with a real LLM in the loop, which side
    # wins cost/tokens can flip run to run (the agent's several small calls
    # vs the workflow's one large call trade off differently depending on
    # the input/output token mix), so the paragraph must follow the actual
    # numbers rather than assume the workflow's fixed 3-tool policy is
    # always the pricier one.
    cheaper_name = "workflow" if wf_total_cost <= agent_total_cost else "agent"

    recommendation = (
        f"Decision rule: does the correct path vary by input? Only "
        f"{n_dep}/{len(scenarios)} questions ({dep_ids_str}) have step 3 "
        f"depend on what step 2 finds (a named parameter changed for a "
        f"target api_version, so check_deprecation must resolve the "
        f"replacement) — the agent actually took that branch on "
        f"{agent_used_check_deprecation}/{n_dep} of them, the workflow "
        f"never branches (it always runs all 3 tools). Even so, that "
        f"variation is one describable rule, not open-ended planning: "
        f"pass rate is {agent_pass_rate:.0%} (agent) vs {wf_pass_rate:.0%} "
        f"(workflow), the {faster_name} is {speed_ratio:.1f}x faster "
        f"({faster_time:.0f}ms vs {slower_time:.0f}ms), and tokens/cost are "
        f"{agent_total_tokens} tok/${agent_total_cost:.4f} (agent) vs "
        f"{wf_total_tokens} tok/${wf_total_cost:.4f} (workflow) - {cheaper_name} "
        f"is cheaper here, but that ordering isn't the point: the branch "
        f"itself is one describable rule, so it belongs hard-coded as a "
        f"conditional in the fixed workflow rather than run through a full "
        f"autonomous loop either way. Verdict: none of these 10 questions "
        f"needs a genuine autonomous loop."
    )

    print(f"{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    print(f"  Agent:     {agent_avg_time:.0f}ms avg (p50={agent_p[50]:.0f}, p99={agent_p[99]:.0f}), "
          f"pass_rate={agent_pass_rate:.0%}, {agent_total_calls} API calls, "
          f"${agent_total_cost:.4f}")
    print(f"  Workflow:  {wf_avg_time:.0f}ms avg (p50={wf_p[50]:.0f}, p99={wf_p[99]:.0f}), "
          f"pass_rate={wf_pass_rate:.0%}, {wf_total_calls} API calls, "
          f"${wf_total_cost:.4f}")
    print(f"  Speed:     {speed_winner} wins")
    print(f"  Cost:      {cost_winner} wins")
    print(f"  Quality:   {quality_winner} wins")
    print(f"  Per-question wins: agent={question_wins['agent']}, "
          f"workflow={question_wins['workflow']}, tie={question_wins['tie']} "
          f"-> overall: {overall_winner}")
    print(f"  Step-3-depends-on-step-2 questions: {dependency_ids} "
          f"({len(dependency_ids)}/10) - agent actually called "
          f"check_deprecation on {agent_used_check_deprecation}/{len(dependency_ids)} of them")
    print(f"{'='*60}\n")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "agent_results": agent_results,
        "workflow_results": workflow_results,
        "recommendation": recommendation,
    }


def _write_csv(results, out_path):
    """The required 8-number comparable table: pass rate, p50 latency,
    tokens, cost/question for each system, plus p99/avg for context."""
    s = results["summary"]
    n = s["total_questions"]
    rows = [
        ["system", "pass_rate", "p50_latency_ms", "p99_latency_ms",
         "avg_latency_ms", "total_est_tokens", "total_est_cost_usd",
         "cost_per_question_usd", "total_questions"],
    ]
    for name in ("agent", "workflow"):
        m = s[name]
        rows.append([
            name, m["pass_rate"], m["p50_latency_ms"], m["p99_latency_ms"],
            m["avg_latency_ms"], m["total_est_tokens"], m["total_est_cost_usd"],
            round(m["total_est_cost_usd"] / n, 6), n,
        ])
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def main():
    quick = "--quick" in sys.argv
    scenarios = _load_scenarios(QUICK_COUNT if quick else SCENARIO_COUNT)

    results = run_race(scenarios)

    # Save results
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(out_dir, "race_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"Results saved to {out_path}")

    csv_path = os.path.join(out_dir, "race.csv")
    _write_csv(results, csv_path)
    print(f"CSV table saved to {csv_path}")


if __name__ == "__main__":
    main()
