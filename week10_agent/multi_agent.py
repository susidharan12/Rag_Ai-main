"""Week 10 · Multi-Agent Squad — Orchestrator + 2 narrow specialists.

The orchestrator decomposes a developer question and delegates to:
  - VersionDeprecationWorker: version-specific facts, deprecation/migration,
    parameter defaults, error-code retryability. Tools: search_docs,
    get_version_info, check_deprecation, get_parameter_default, get_error_info.
  - CodeSampleWorker: usage/code samples. Tools: search_docs, get_version_info,
    compare_versions (deliberately NOT the full single-agent toolbelt — the
    narrow-prompt / fewer-tools constraint is the only plausible source of a win).

Context strategy (stated so the race tests the PATTERN, not a sloppy hand-off):
  * The orchestrator sends each worker a compact BRIEF — question, the resolved
    target SDK version, and the named subject — never the corpus. The target
    version always travels with the brief so a worker can't emit a v2 sample
    for a v3 question.
  * Workers return a short cited answer, not their retrieved chunks.
  * With ONE worker the orchestrator passes its answer through (no extra LLM
    hop); with TWO it makes one synthesis call over the two short answers.

Failure policy: a worker HTTP 5xx is retried once; if it still fails the
orchestrator degrades to a partial answer that says the version check is
missing — it never ships a sample as if it had been version-checked.

Every LLM call is metered at the Groq chokepoint (see meter.py); every
delegation is logged to Orchestrator.handoffs with its token counts.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from rag_core import generators, settings
from rag_core.agent import _execute_tool, _extract_subject
from rag_core.generators import build_context
from rag_core.store import DocStore
from rag_core.telemetry import estimate_tokens

from week10_agent import meter

REFUSAL = "I could not find the answer in the provided documents."
_VERSION_RE = re.compile(r"\b(?:sdk\s+)?v([23])\b|\b([23])\.x\b", re.IGNORECASE)
_CODE_ROUTE = ("explain", "how do i", "how does", "how to", "example", "sample",
               "snippet", "usage", "code", "implement", "show me")
MAX_WORKER_CHUNKS = 6
RETRY_BACKOFF_S = 1.0


class WorkerHTTPError(Exception):
    """A worker answered with an HTTP error status (real or injected)."""

    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def _llm(system: str, user: str, max_tokens: int = 700) -> str:
    """One metered LLM completion via the shared Groq chokepoint."""
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "top_p": 0.9,
    }
    message = generators._post_groq_with_retry(payload)
    text = (message.get("content") or "").strip() or (message.get("reasoning") or "").strip()
    return text


def _dedupe(results: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for r in results:
        if r["chunk_id"] in seen:
            continue
        seen.add(r["chunk_id"])
        out.append(r)
    return out


class _Worker:
    name = "worker"
    system_prompt = ""

    def __init__(self, store: DocStore):
        self.store = store

    def gather(self, brief: Dict) -> List[Dict]:
        raise NotImplementedError

    def handle(self, brief: Dict) -> Dict:
        with meter.scope(self.name):
            chunks = _dedupe(self.gather(brief))[:MAX_WORKER_CHUNKS]
            user = (f"Target SDK version: {brief['target_version']}\n"
                    f"Question: {brief['question']}\n\n"
                    f"Context:\n{build_context(chunks) if chunks else '(none retrieved)'}")
            answer = _llm(self.system_prompt, user)
            call = meter.last_call()
        return {"answer": answer, "chunks": chunks,
                "llm_in": call["in"], "llm_out": call["out"],
                "llm_latency_ms": call["latency_ms"]}


class VersionDeprecationWorker(_Worker):
    name = "version_deprecation_worker"
    system_prompt = (
        "You are the version/deprecation specialist for the Nimbus SDK docs. "
        "Answer ONLY version-specific facts, deprecation/migration, parameter "
        "defaults and error-code retryability, for the target SDK version you "
        "are given. Use only the context; quote exact values; cite sources as "
        "[source_doc]. Do not write code samples. If the context does not "
        f'contain the answer, reply exactly: "{REFUSAL}"')

    def __init__(self, store, inject_failure_for: Optional[str] = None,
                 inject_status: int = 500):
        super().__init__(store)
        self.inject_failure_for = inject_failure_for
        self.inject_status = inject_status

    def gather(self, brief):
        q, ver, subject = brief["question"], brief["target_version"], brief.get("subject")
        results = []
        results += _execute_tool("search_docs", {"query": q}, self.store)[1]
        results += _execute_tool("get_version_info", {"version": ver, "query": q}, self.store)[1]
        if subject:
            results += _execute_tool("check_deprecation",
                                     {"subject": subject, "api_version": ver}, self.store)[1]
            if re.search(r"\b(default|type|maximum|max)\b", q, re.IGNORECASE):
                results += _execute_tool("get_parameter_default",
                                         {"param": subject, "query": q}, self.store)[1]
        code = re.search(r"\b(?:error code|http)\s*(\d{3})\b", q, re.IGNORECASE)
        if code:
            results += _execute_tool("get_error_info",
                                     {"code": code.group(1), "query": q}, self.store)[1]
        return results

    def handle(self, brief):
        if self.inject_failure_for and brief.get("case_id") == self.inject_failure_for:
            raise WorkerHTTPError(self.inject_status,
                                  "Internal Server Error (injected fault)")
        return super().handle(brief)


class CodeSampleWorker(_Worker):
    name = "code_sample_worker"
    system_prompt = (
        "You are the code-sample specialist for the Nimbus SDK docs. Produce a "
        "short, parseable Python usage snippet plus a one-or-two sentence "
        "explanation, written for the target SDK version you are given (never "
        "mix v2 and v3 APIs). Use only the context; cite sources as "
        f'[source_doc]. If the context cannot support it, reply exactly: "{REFUSAL}"')

    def gather(self, brief):
        q, ver = brief["question"], brief["target_version"]
        results = _execute_tool("search_docs", {"query": q + " example usage"}, self.store)[1]
        results += _execute_tool("get_version_info",
                                 {"version": ver, "query": q + " example"}, self.store)[1]
        if brief.get("compare"):
            results += _execute_tool("compare_versions", {"query": q}, self.store)[1]
        return results


class Orchestrator:
    name = "orchestrator"
    synth_prompt = (
        "You are the orchestrator of a docs squad. Merge the specialists' "
        "answers into ONE final answer. Keep every exact value and [source] "
        "citation, and keep the code from the code-sample specialist. Do not "
        "add facts not present in the specialist answers. If every specialist "
        f'refused, reply exactly: "{REFUSAL}"')

    def __init__(self, store: DocStore, inject_failure_for: Optional[str] = None,
                 inject_status: int = 500, max_retries: int = 1):
        self.store = store
        self.version_worker = VersionDeprecationWorker(store, inject_failure_for, inject_status)
        self.code_worker = CodeSampleWorker(store)
        self.max_retries = max_retries
        self.handoffs: List[Dict] = []

    # -- routing ------------------------------------------------------------
    def route(self, question: str) -> Dict[str, Any]:
        q = question.lower()
        versions = [a or b for a, b in _VERSION_RE.findall(question)]
        target = f"v{versions[-1]}" if versions else "v3"  # v3 = current when unstated
        both = len(set(versions)) >= 2
        return {
            "workers": ["version"] + (["code"] if any(k in q for k in _CODE_ROUTE) else []),
            "target_version": target,
            "version_explicit": bool(versions),
            "subject": _extract_subject(question),
            "compare": both or "changed" in q or "between" in q,
        }

    # -- hop logging --------------------------------------------------------
    def _log(self, **row):
        row["total_tokens"] = row.get("llm_in", 0) + row.get("llm_out", 0)
        self.handoffs.append(row)

    def _delegate(self, worker: _Worker, brief: Dict, case_id: str):
        """Call a worker; retry on HTTP 5xx; log every attempt as a hop."""
        brief_tokens = sum(estimate_tokens(str(v)) for v in brief.values())
        attempts = 1 + self.max_retries
        last_err = None
        for attempt in range(1, attempts + 1):
            t0 = time.perf_counter()
            try:
                res = worker.handle(brief)
                self._log(case_id=case_id, hop=f"orchestrator -> {worker.name}",
                          attempt=attempt, brief_tokens=brief_tokens,
                          llm_in=res["llm_in"], llm_out=res["llm_out"],
                          return_tokens=estimate_tokens(res["answer"]),
                          latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                          status="ok", note="")
                return res, None
            except (WorkerHTTPError, Exception) as exc:  # noqa: BLE001 - any worker fault
                last_err = exc
                self._log(case_id=case_id, hop=f"orchestrator -> {worker.name}",
                          attempt=attempt, brief_tokens=brief_tokens, llm_in=0, llm_out=0,
                          return_tokens=0,
                          latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                          status="error", note=str(exc)[:120])
                retryable = isinstance(exc, WorkerHTTPError) and exc.status >= 500
                if attempt < attempts and retryable:
                    time.sleep(RETRY_BACKOFF_S)
                    continue
                break
        return None, last_err

    # -- main ---------------------------------------------------------------
    def run(self, question: str, case_id: str = "") -> Dict[str, Any]:
        t0 = time.perf_counter()
        plan = self.route(question)
        brief = {"case_id": case_id, "question": question,
                 "target_version": plan["target_version"],
                 "subject": plan["subject"], "compare": plan["compare"]}

        jobs = {"version": self.version_worker}
        if "code" in plan["workers"]:
            jobs["code"] = self.code_worker
        if len(jobs) > 1:
            with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                futures = {k: pool.submit(self._delegate, w, brief, case_id)
                           for k, w in jobs.items()}
                outcomes = {k: f.result() for k, f in futures.items()}
        else:
            outcomes = {"version": self._delegate(self.version_worker, brief, case_id)}

        ok = {k: res for k, (res, err) in outcomes.items() if res}
        errors = {k: err for k, (res, err) in outcomes.items() if err}
        retries = sum(1 for h in self.handoffs
                      if h["case_id"] == case_id and h["attempt"] > 1)
        status = "ok"
        caveat = ""

        if "version" in errors:
            status = "degraded" if ok else "failed"
            caveat = (f"[PARTIAL ANSWER] The version/deprecation check failed "
                      f"({errors['version']}) after {retries} retry, so this answer "
                      f"was NOT verified against an SDK version "
                      f"({'assumed ' + plan['target_version'] if not plan['version_explicit'] else 'asked: ' + plan['target_version']}). "
                      f"Please confirm which SDK version you are on (v2 or v3).")
        elif errors:
            status = "degraded"
            caveat = "[PARTIAL ANSWER] The code-sample worker failed; no sample is included."

        if not ok:
            answer = caveat or REFUSAL
        elif len(ok) == 1:
            answer = next(iter(ok.values()))["answer"]  # pass-through: no extra LLM hop
        else:
            with meter.scope("orchestrator_synthesis"):
                s0 = time.perf_counter()
                body = "\n\n".join(f"[{k} specialist]\n{r['answer']}" for k, r in ok.items())
                answer = _llm(self.synth_prompt, f"Question: {question}\n\n{body}")
                call = meter.last_call()
            self._log(case_id=case_id, hop="workers -> orchestrator synthesis (resend)",
                      attempt=1,
                      brief_tokens=sum(estimate_tokens(r["answer"]) for r in ok.values()),
                      llm_in=call["in"], llm_out=call["out"],
                      return_tokens=estimate_tokens(answer),
                      latency_ms=round((time.perf_counter() - s0) * 1000, 1),
                      status="ok", note="")
        if caveat and ok:
            answer = f"{caveat}\n\n{answer}"

        # Chunks that two different agents each had to receive = re-sent context.
        seen: Dict[str, int] = {}
        dup_tokens = 0
        for res in ok.values():
            for c in res["chunks"]:
                if c["chunk_id"] in seen:
                    dup_tokens += estimate_tokens(c["text"])
                seen[c["chunk_id"]] = 1

        return {"answer": answer, "status": status, "plan": plan, "retries": retries,
                "errors": {k: str(v) for k, v in errors.items()},
                "duplicate_chunk_tokens": dup_tokens,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}


def run_multi_agent(question: str, store: DocStore, case_id: str = "",
                    inject_failure_for: Optional[str] = None):
    orch = Orchestrator(store, inject_failure_for=inject_failure_for)
    res = orch.run(question, case_id=case_id)
    res["handoffs"] = orch.handoffs
    return res


def run_single_agent(question: str, store: DocStore) -> Dict[str, Any]:
    """The Week 7 single ReAct agent, unchanged."""
    from rag_core.agent import run_agent
    res = run_agent(question, store, max_steps=4, time_budget=30)
    return {"answer": res["answer"], "latency_ms": res["metrics"]["latency_ms"],
            "steps": res["steps"], "stopped_by": res["metrics"]["stopped_by"],
            "tools_used": res["metrics"]["tools_used"]}
