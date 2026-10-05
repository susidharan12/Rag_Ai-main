"""Week 10 · Race — single ReAct agent vs. Orchestrator squad.

    python -m week10_agent.race            # full 10-case race + failure injection
    python -m week10_agent.race --smoke    # 2 cases, writes nothing (infra check)

Same 10 Week-6 cases (eval/eval_cases.json, Track E, no new cases written),
same generator model, same deterministic judge (the Week-6 eval's own
`app_pass` rule from eval/run_eval.py), same index. Both arms are metered at
the Groq chokepoint (meter.py). Each case runs ONCE; nothing is re-run to
get a better result.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)
os.environ["RAG_DATA_DIR"] = os.path.join(REPO_ROOT, "eval", ".eval_index")

from rag_core import settings  # noqa: E402
from rag_core.store import DocStore, get_embedding_model  # noqa: E402
from rag_core.telemetry import estimate_cost_usd, percentiles  # noqa: E402
from week10_agent import meter  # noqa: E402
from week10_agent.multi_agent import REFUSAL, run_multi_agent, run_single_agent  # noqa: E402

CASES_PATH = os.path.join(REPO_ROOT, "eval", "eval_cases.json")

# Chosen BEFORE any run: a stratified 10 of the 28 Week-6 cases (3 factual,
# 3 conceptual, 1 unsupported, 2 version-specific, 1 ambiguous). Not tuned to
# either arm.
SELECTED = ["eval_001", "eval_004", "eval_010", "eval_014", "eval_016",
            "eval_017", "eval_019", "eval_023", "eval_025", "eval_026"]
FAILURE_CASE = "eval_014"  # routed to BOTH workers: version check + code sample


def judge(case, answer):
    """Week-6 eval/run_eval.py::run_case pass rule, same in effect."""
    refused = REFUSAL.lower() in answer.lower()
    if case["expect"] == "refuse":
        return refused
    return (not refused) and all(t.lower() in answer.lower()
                                 for t in case.get("expected_tokens", []))


def load_cases():
    cases = {c["id"]: c for c in json.load(open(CASES_PATH, encoding="utf-8"))["cases"]}
    return [cases[i] for i in SELECTED]


def arm_summary(rows):
    p = percentiles([r["latency_ms"] for r in rows])
    tin = sum(r["input_tokens"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)
    cost = sum(r["cost_usd"] for r in rows)
    return {
        "pass": sum(r["passed"] for r in rows), "n": len(rows),
        "p50_ms": round(p[50]), "p99_ms": round(p[99]),
        "input_tokens": tin, "output_tokens": tout, "total_tokens": tin + tout,
        "cost_total": round(cost, 6), "cost_per_q": round(cost / len(rows), 6),
        "llm_calls": sum(r["llm_calls"] for r in rows),
        "llm_errors": sum(r["llm_errors"] for r in rows),
    }


def run_race(store, cases, pause):
    single, multi, handoffs = [], [], []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']}: {case['question'][:70]}", flush=True)
        q = case["question"]

        m0 = meter.mark()
        t0 = time.perf_counter()
        with meter.scope("single_agent"):
            sres = run_single_agent(q, store)
        s_lat = round((time.perf_counter() - t0) * 1000, 1)
        sm = meter.summarize(meter.since(m0))
        single.append({"id": case["id"], "latency_ms": s_lat,
                       "passed": judge(case, sres["answer"]),
                       "answer": sres["answer"], "tools": sres["tools_used"], **sm})
        print(f"   single: {s_lat:.0f}ms {sm['total_tokens']}tok err={sm['llm_errors']} "
              f"{'PASS' if single[-1]['passed'] else 'FAIL'}", flush=True)
        time.sleep(pause)

        m0 = meter.mark()
        t0 = time.perf_counter()
        mres = run_multi_agent(q, store, case_id=case["id"])
        m_lat = round((time.perf_counter() - t0) * 1000, 1)
        mm = meter.summarize(meter.since(m0))
        multi.append({"id": case["id"], "latency_ms": m_lat,
                      "passed": judge(case, mres["answer"]),
                      "answer": mres["answer"], "status": mres["status"],
                      "workers": mres["plan"]["workers"], "retries": mres["retries"],
                      "duplicate_chunk_tokens": mres["duplicate_chunk_tokens"], **mm})
        handoffs.extend(mres["handoffs"])
        print(f"   multi : {m_lat:.0f}ms {mm['total_tokens']}tok err={mm['llm_errors']} "
              f"workers={mres['plan']['workers']} "
              f"{'PASS' if multi[-1]['passed'] else 'FAIL'}", flush=True)
        time.sleep(pause)
    return single, multi, handoffs


def reconcile(multi, handoffs):
    """Drop tokens the first race run billed for errored (HTTP 429) calls.

    The race was run before meter.summarize stopped counting errored calls.
    Those calls have out=0 and never reached a hop row, so the unbilled
    amount is exactly (row total - sum of that case's hop totals).
    meter.summarize now excludes them, so for fresh runs this is a no-op.
    """
    for row in multi:
        hop_total = sum(h["total_tokens"] for h in handoffs if h["case_id"] == row["id"])
        unbilled = row["total_tokens"] - hop_total
        if unbilled:
            row["input_tokens"] -= unbilled
            row["total_tokens"] = hop_total
            row["cost_usd"] = estimate_cost_usd(row["input_tokens"], row["output_tokens"])
            row["unbilled_error_tokens_removed"] = unbilled
    return multi


def run_failure(store, cases):
    case = next(c for c in cases if c["id"] == FAILURE_CASE)
    m0 = meter.mark()
    t0 = time.perf_counter()
    res = run_multi_agent(case["question"], store, case_id=case["id"],
                          inject_failure_for=FAILURE_CASE)
    lat = round((time.perf_counter() - t0) * 1000, 1)
    return case, res, lat, meter.summarize(meter.since(m0))


def fmt_ms(ms):
    return f"{ms / 1000:.1f}s"


def write_race_table(cases, single, multi, ss, ms, mult, top, path):
    L = ["# Week 10 — Race table: single agent vs. orchestrator squad\n",
         f"Same 10 Week-6 cases (`eval/eval_cases.json`, stratified pick, no new cases), same "
         f"generator model (`{settings.GROQ_MODEL}`), same deterministic judge (Week-6 "
         f"`run_eval.py` pass rule), same index. Each case run once. Tokens/cost are metered per "
         f"LLM call at the Groq boundary for BOTH arms (est. ~4 chars/token; "
         f"${settings.PRICE_PER_1K_INPUT * 1000:.2f}/M in, ${settings.PRICE_PER_1K_OUTPUT * 1000:.2f}/M out).\n",
         "| Metric | Single agent (ReAct) | Orchestrator squad |", "|---|---|---|",
         f"| Pass rate | {ss['pass']}/{ss['n']} = {ss['pass'] / ss['n']:.0%} | {ms['pass']}/{ms['n']} = {ms['pass'] / ms['n']:.0%} |",
         f"| p50 latency | {fmt_ms(ss['p50_ms'])} | {fmt_ms(ms['p50_ms'])} |",
         f"| p99 latency | {fmt_ms(ss['p99_ms'])} | {fmt_ms(ms['p99_ms'])} |",
         f"| Total tokens (in + out) | {ss['total_tokens']:,} ({ss['input_tokens']:,} + {ss['output_tokens']:,}) | {ms['total_tokens']:,} ({ms['input_tokens']:,} + {ms['output_tokens']:,}) |",
         f"| Cost per question | ${ss['cost_per_q']:.6f} | ${ms['cost_per_q']:.6f} |",
         f"| Cost, all 10 | ${ss['cost_total']:.6f} | ${ms['cost_total']:.6f} |",
         f"| LLM calls (errored) | {ss['llm_calls']} ({ss['llm_errors']}) | {ms['llm_calls']} ({ms['llm_errors']}) |",
         "",
         f"**Context re-send multiplier: {mult:.1f}x** ({ms['total_tokens']:,} multi / "
         f"{ss['total_tokens']:,} single tokens). Largest share: `{top[0]}` — "
         f"{top[1]:.0f}% of all multi-agent tokens.",
         "",
         "p99 note: with 10 samples, nearest-rank p99 is simply the slowest case.\n",
         "## Per-case results\n",
         "| Case | Mode | Single | tokens | latency | Multi | tokens | latency | workers | status |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for c, s, m in zip(cases, single, multi):
        L.append(f"| {c['id']} | {c['mode']} | {'PASS' if s['passed'] else 'FAIL'} | "
                 f"{s['total_tokens']} | {fmt_ms(s['latency_ms'])} | "
                 f"{'PASS' if m['passed'] else 'FAIL'} | {m['total_tokens']} | "
                 f"{fmt_ms(m['latency_ms'])} | {'+'.join(m['workers'])} | {m['status']} |")
    dup = sum(m["duplicate_chunk_tokens"] for m in multi)
    degraded = [m["id"] for m in multi if m["status"] != "ok"]
    L += ["\n## Read these before quoting the numbers\n",
          f"- **{len(degraded)} of 10 squad answers were degraded, not clean** ({', '.join(degraded) or 'none'}): "
          "the parallel fan-out burst Groq's tokens-per-minute limit and one worker got HTTP 429. "
          "The orchestrator only retries 5xx, not 429, so it returned a labelled partial answer. "
          "The judge still passed them because the expected token was present, so clean full answers are "
          f"{10 - len(degraded)}/10. Errored calls are not billed as tokens. Not re-run.",
          f"- **The savings are mostly 'no LLM planner', not 'many agents'.** The single agent made "
          f"{ss['llm_calls']} LLM calls for 10 questions (ReAct planning steps + answer synthesis, each "
          f"re-sending context); the squad routes and retrieves deterministically and made "
          f"{ms['llm_calls'] - ms['llm_errors']} billed calls. This race compares a ReAct loop against "
          "fixed routing plus two prompts; it does not isolate the multi-agent pattern. A fixed "
          "workflow would probably land near the squad's numbers (not tested here).",
          f"- Re-sent context paid twice: {dup} chunk tokens were retrieved by BOTH workers; "
          "the synthesis hop re-sends both worker answers (see handoffs.log).",
          "- Routing false positive: eval_010 ('error **code** 500') matched the code-sample keyword, "
          "so a code worker ran for a yes/no fact (~750 tokens for nothing).",
          "- Single-agent miss: eval_019 (Go client) FAIL: it answered with a Python snippet instead of refusing.",
          "- Tokens are ~4 chars/token estimates on both arms; p99 over 10 samples is the max.",
          "- The squad's p99 (12.2s) is eval_016's code worker; its p50 is a single one-LLM-call hop."]
    L.append("\n## Cases\n")
    for c in cases:
        L.append(f"- **{c['id']}** ({c['mode']}, expect `{c['expect']}`): {c['question']}")
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


def write_handoffs(handoffs, ms, ss, path):
    by_hop = defaultdict(int)
    for h in handoffs:
        by_hop[h["hop"]] += h["total_tokens"]
    total = sum(by_hop.values())
    L = ["# handoffs.log — every orchestrator hop, per-hop token counts (est. tokens)",
         "# brief = tokens the orchestrator sent; llm_in/out = the callee's metered LLM call "
         "(llm_in INCLUDES the re-sent retrieved context); ret = tokens handed back upstream.",
         "case_id   hop                                        try  brief  llm_in llm_out  total   ret  latency  status"]
    for h in handoffs:
        L.append(f"{h['case_id']:<9} {h['hop']:<42} {h['attempt']:>3} {h['brief_tokens']:>6} "
                 f"{h['llm_in']:>7} {h['llm_out']:>7} {h['total_tokens']:>6} {h['return_tokens']:>5} "
                 f"{h['latency_ms']:>7.0f}ms  {h['status']} {h['note']}")
    L += ["", "# per-hop totals across the race"]
    for hop, tok in sorted(by_hop.items(), key=lambda kv: -kv[1]):
        L.append(f"{hop:<46} {tok:>7} tokens = {tok / total * 100:5.1f}% of all multi-agent tokens")
    mult = ms["total_tokens"] / ss["total_tokens"]
    top = max(by_hop.items(), key=lambda kv: kv[1])
    L += ["",
          f"hop-sum check: {total} tokens logged vs {ms['total_tokens']} metered "
          f"({'match' if total == ms['total_tokens'] else 'MISMATCH'})",
          f"MULTIPLIER: {ms['total_tokens']} multi / {ss['total_tokens']} single = {mult:.1f}x",
          f"LARGEST HOP: {top[0]}: {top[1] / total * 100:.0f}% of total tokens"]
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return mult, (top[0], top[1] / total * 100)


def write_failure(case, res, lat, summ, path):
    retried = res["retries"] > 0
    caveat = "[PARTIAL ANSWER]" in res["answer"]
    shipped_code = "```" in res["answer"] or "client." in res["answer"].lower()
    if res["status"] == "failed":
        verdict = "FAILED — returned an error/partial notice, no answer"
    elif retried and caveat:
        verdict = ("RETRIED once, then DEGRADED to a partial answer that disclosed the missing "
                   "version check (did not lie)")
    elif not caveat and shipped_code:
        verdict = "LIED — shipped a code sample with no version check behind it and no disclosure"
    else:
        verdict = "OTHER — see trace"
    L = [f"# Failure injection — version/deprecation worker returns HTTP 500 on {case['id']}\n",
         f"Case: `{case['id']}` ({case['mode']}): {case['question']}",
         "Fault: `VersionDeprecationWorker.handle` raises `HTTP 500: Internal Server Error` on EVERY "
         "attempt for this case (persistent fault, so a retry cannot succeed). Code-sample worker "
         "healthy. This case is routed to both workers, so a sample CAN be produced without a "
         "version check — the exact risk under test. It is run as an extra run, outside the 10-case "
         "race numbers.\n",
         f"## One-line verdict\n\n**{verdict}.**\n",
         "## What the orchestrator actually did (hop trace)\n",
         "| hop | try | status | tokens | note |", "|---|---|---|---|---|"]
    for h in res["handoffs"]:
        L.append(f"| {h['hop']} | {h['attempt']} | {h['status']} | {h['total_tokens']} | {h['note']} |")
    L += ["",
          f"- retries on the failed worker: **{res['retries']}** (policy: retry once on 5xx, 1s backoff)",
          f"- final status: **{res['status']}**",
          f"- partial-answer caveat present: **{caveat}**; code sample in answer: **{shipped_code}**",
          f"- latency {fmt_ms(lat)}, {summ['total_tokens']} tokens, ${summ['cost_usd']:.6f}",
          f"- judged against the Week-6 rule: **{'PASS' if judge(case, res['answer']) else 'FAIL'}** "
          f"(expected tokens {case.get('expected_tokens')})",
          "", "## Final answer returned to the developer\n", "```", res["answer"], "```", "",
          "## Caveats\n",
          "- The retry-then-degrade policy is a design choice written into the orchestrator, so this "
          "records that policy's real behavior, not an accident. An orchestrator with no retry and "
          "no caveat would have returned the code sample alone — the 'lie' branch this test detects.",
          "- The fault is persistent; a transient (fail-once) fault was not tested."]
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--from-json", action="store_true",
                    help="regenerate race_table.md / handoffs.log from race_results.json (no LLM calls)")
    ap.add_argument("--pause", type=float, default=8.0,
                    help="seconds between runs (outside timing) to ease Groq TPM limits")
    args = ap.parse_args()

    if args.from_json:
        d = json.load(open(os.path.join(HERE, "race_results.json"), encoding="utf-8"))
        cases, single, handoffs = load_cases(), d["single"], d["handoffs"]
        multi = reconcile(d["multi"], handoffs)
        ss, ms = arm_summary(single), arm_summary(multi)
        d.update(multi=multi, single_summary=ss, multi_summary=ms)
        json.dump(d, open(os.path.join(HERE, "race_results.json"), "w", encoding="utf-8"), indent=2)
        mult, top = write_handoffs(handoffs, ms, ss, os.path.join(HERE, "handoffs.log"))
        write_race_table(cases, single, multi, ss, ms, mult, top, os.path.join(HERE, "race_table.md"))
        print(ss, ms, f"{mult:.1f}x", top, sep=chr(10))
        return

    meter.install()
    store = DocStore()
    store.ensure_loaded()
    get_embedding_model()
    store.search("warmup", top_k=1)
    cases = load_cases()
    if args.smoke:
        cases = [c for c in cases if c["id"] in ("eval_001", "eval_014")]
    print(f"model={settings.GROQ_MODEL} docs={store.stats()['documents']} cases={len(cases)}")

    single, multi, handoffs = run_race(store, cases, args.pause)
    ss, ms = arm_summary(single), arm_summary(multi)
    print("single", ss)
    print("multi ", ms)
    if args.smoke:
        return

    json.dump({"model": settings.GROQ_MODEL, "cases": SELECTED, "single": single, "multi": multi,
               "single_summary": ss, "multi_summary": ms, "handoffs": handoffs},
              open(os.path.join(HERE, "race_results.json"), "w", encoding="utf-8"), indent=2)
    mult, top = write_handoffs(handoffs, ms, ss, os.path.join(HERE, "handoffs.log"))
    write_race_table(cases, single, multi, ss, ms, mult, top, os.path.join(HERE, "race_table.md"))
    print(f"multiplier {mult:.1f}x; largest hop {top[0]} {top[1]:.0f}%")

    time.sleep(args.pause)
    case, res, lat, summ = run_failure(store, cases)
    print("failure:", write_failure(case, res, lat, summ, os.path.join(HERE, "failure_case.md")))


if __name__ == "__main__":
    main()
