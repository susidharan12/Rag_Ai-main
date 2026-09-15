"""Week 7 · Agent Loop — ReAct-style agent with Chain of Thought.

Implements the plan -> act -> observe -> repeat loop where an LLM
decides the next step at each iteration. Every step is logged so the
UI can display the full reasoning chain.

Stop conditions (circuit breakers so the loop can never run forever,
overspend, or crash on a malformed tool call):
  - max_steps (default 5)       — hard cap on iterations
  - time_budget (default 30s)   — wall-clock limit
  - max_tokens (default 6000)   — cumulative estimated token budget
  - max_cost_usd (default 0.01) — cumulative estimated $ budget
  - schema_error (2 strikes)    — repeated malformed tool calls abort cleanly
  - finish tool                 — agent judges it has enough info, stops early
  - parse failure                — malformed LLM output stops the loop safely
"""

import json
import re
import time
from enum import Enum

from pydantic import BaseModel, ValidationError

from rag_core import settings
from rag_core.telemetry import estimate_cost_usd, estimate_tokens

# ---------------------------------------------------------------------------
# Tool definitions — each tool has a name, description, strict arg schema,
# and an execute function.
# ---------------------------------------------------------------------------

TOOL_DESCRIPTIONS = {
    "search_docs": (
        "Search the indexed documentation for chunks relevant to a query. "
        "Returns the top matching text chunks with source info."
    ),
    "get_version_info": (
        "Get documentation chunks specific to a named version (e.g. 'v2', "
        "'v3', or an API version string). Use when the question asks about "
        "one specific version."
    ),
    "compare_versions": (
        "Retrieve documentation for two versions side by side. "
        "Use when the question asks for differences or changes between versions."
    ),
    "get_error_info": (
        "Look up error code information (HTTP status codes, error names, "
        "retryability). Use for questions about specific error codes."
    ),
    "get_parameter_default": (
        "Look up a specific parameter's default value, type, and description "
        "from the parameter tables. Use for questions about parameter defaults."
    ),
    # Week 7 · Task Set E — third tool. Single job only: given a named
    # endpoint/parameter/feature that you already identified and a specific
    # target api_version, report whether it was removed/changed/replaced in
    # that version and name the replacement. This is deliberately narrower
    # than compare_versions (which dumps both versions' raw docs for the
    # caller to diff by eye) and than get_version_info (which dumps one
    # version's raw docs) — it is the single follow-up fact lookup an agent
    # reaches for once it already knows *what* changed and needs to know
    # *what replaced it*, not a second way to browse the docs.
    "check_deprecation": (
        "Check whether one specific named endpoint, parameter, or CLI flag "
        "was removed, changed, or replaced in a given target api_version, "
        "and return its replacement if one exists. Use ONLY as a follow-up "
        "once you already know the subject and the target version from an "
        "earlier step — not for open-ended searching or side-by-side "
        "version comparison."
    ),
    "finish": (
        "Return the final answer to the user. Call this when you have "
        "gathered enough information to answer the question."
    ),
}


# Strict, type-safe argument schemas (Week 7 deliverable: prevent
# execution-time failures from malformed tool calls instead of discovering
# them as a crash or a silently wrong lookup).
class SearchDocsArgs(BaseModel):
    query: str


class GetVersionInfoArgs(BaseModel):
    version: str
    query: str = ""


class CompareVersionsArgs(BaseModel):
    query: str = "differences between versions"


class GetErrorInfoArgs(BaseModel):
    code: str = ""
    query: str = ""


class GetParameterDefaultArgs(BaseModel):
    param: str = ""
    query: str = ""


# Closed set of api_version values this corpus actually documents (GitHub
# REST API's two version headers, plus Swagger Codegen's two major lines).
# An enum here (rather than a free string, as get_version_info/
# compare_versions use) means a malformed/hallucinated version string is
# rejected by _validate_tool_args as a schema error instead of silently
# searching for the wrong thing.
class ApiVersion(str, Enum):
    GITHUB_2022_11_28 = "2022-11-28"
    GITHUB_2025_06_01 = "2025-06-01"
    SWAGGER_V2 = "2.x"
    SWAGGER_V3 = "3.x"


class CheckDeprecationArgs(BaseModel):
    subject: str
    api_version: ApiVersion


class FinishArgs(BaseModel):
    answer: str


TOOL_SCHEMAS = {
    "search_docs": SearchDocsArgs,
    "get_version_info": GetVersionInfoArgs,
    "compare_versions": CompareVersionsArgs,
    "get_error_info": GetErrorInfoArgs,
    "get_parameter_default": GetParameterDefaultArgs,
    "check_deprecation": CheckDeprecationArgs,
    "finish": FinishArgs,
}


def _validate_tool_args(tool_name, args):
    """Validate args against the tool's strict schema.

    Returns (ok, cleaned_args_or_error_message). Never raises — a malformed
    call becomes a clear observation for the agent (or a clean loop abort
    after repeated failures), not a crash.
    """
    schema = TOOL_SCHEMAS.get(tool_name)
    if schema is None:
        return False, f"Unknown tool '{tool_name}'. Valid tools: {sorted(TOOL_SCHEMAS)}."
    try:
        validated = schema(**(args or {}))
    except ValidationError as e:
        return False, f"Invalid arguments for '{tool_name}': {e.errors()[0]['msg']}"
    return True, validated.model_dump()


def _tool_signature(tool_name):
    """The tool's exact expected JSON argument keys, derived straight from
    its Pydantic schema — e.g. "compare_versions(query)". Without this, a
    model has to guess argument names from the prose description alone and
    reliably guesses something plausible-but-wrong (observed live:
    compare_versions called with "version1"/"version2" instead of the
    actual "query" field, which Pydantic then silently drops as an unknown
    extra field, losing the real question context for that tool call)."""
    schema = TOOL_SCHEMAS[tool_name]
    return ", ".join(schema.model_fields.keys())


def _build_system_prompt():
    """Build the ReAct system prompt with tool descriptions.

    Deliberately domain-agnostic: this agent runs over whatever the user has
    indexed (developer docs, SDK references, or any other uploaded
    document), not a fixed corpus.
    """
    tools_block = "\n".join(
        f"  - {name}({_tool_signature(name)}): {desc}"
        for name, desc in TOOL_DESCRIPTIONS.items()
    )
    return f"""You are a documentation research agent. You answer questions about the user's indexed documents.

You answer questions by reasoning step-by-step (Chain of Thought) and using tools.

Available tools:
{tools_block}

At each step, output EXACTLY this JSON format:
{{"thought": "your reasoning about what to do next", "tool": "tool_name", "args": {{"key": "value"}}}}

When you have enough information, use the "finish" tool:
{{"thought": "I now have enough information to answer", "tool": "finish", "args": {{"answer": "your complete answer"}}}}

RULES:
1. Always start by searching the docs unless the question is very specific.
2. Think step by step — explain WHY you chose each tool.
3. Build on previous observations — don't repeat the same search.
4. Use finish ONLY when you are confident in your answer.
5. If the docs don't contain the answer, say so honestly in your finish step.
6. Output ONLY the JSON object, no extra text.
7. If an earlier observation shows a specific endpoint/parameter changed for
   a target api_version, call check_deprecation next to find its replacement
   before finishing — don't guess the replacement from a partial excerpt.
8. "thought" is a ONE-SENTENCE reason for the next tool call (under 25
   words) — never write the final answer there. The full answer belongs
   ONLY in the finish step's "answer" field, once you actually call finish.
9. "args" must use EXACTLY the parameter names shown in parentheses after
   each tool's name above (e.g. compare_versions takes "query", not
   "version1"/"version2") — an unrecognized key is silently dropped, not
   an error, so a wrong name quietly loses your intended input.
"""


# ---------------------------------------------------------------------------
# Tool execution — wraps the existing RAG store and generators
# ---------------------------------------------------------------------------

def _execute_tool(tool_name, args, store):
    """Execute a tool.

    Returns (display_string, raw_results) — display_string is the formatted
    text shown in the UI's Observation panel; raw_results is the actual list
    of retrieval-result dicts (chunk_id/source_doc/page_number/score/text),
    or [] for tools that don't retrieve chunks. Keeping the two separate
    matters: raw_results (not the "--- Chunk N: file, page P (score: X) ---"
    display formatting) is what answer synthesis should ever read as prose —
    otherwise the debug header itself gets picked up as a candidate sentence.
    """
    if tool_name == "search_docs":
        query = args.get("query", "")
        results = store.search(query, top_k=5)
        if not results:
            return "No relevant documentation found.", []
        chunks = []
        for i, r in enumerate(results, 1):
            version = r.get("sdk_version", "")
            vtag = f" [{version}]" if version else ""
            chunks.append(
                f"--- Chunk {i}: {r['source_doc']}, page {r['page_number']}{vtag} "
                f"(score: {r['score']:.3f}) ---\n{r['text'][:600]}"
            )
        return "\n\n".join(chunks), results

    elif tool_name == "get_version_info":
        version = args.get("version", "v3")
        query = args.get("query") or version
        results = store.search(query, top_k=8)
        # NOTE: metadata-only, matching the original behavior on purpose.
        # A text/filename-based fallback (tried during Task Set E work — see
        # week7_agent/README.md "known limitations") does surface real
        # version-specific chunks, but feeding them into _synthesize_answer's
        # shared candidate pool alongside step 0's chunks measurably *hurt*
        # answer quality here: the deterministic extractive picker scores
        # candidates by keyword overlap, and extra on-topic-but-not-quite
        # chunks can outscore the chunk that actually answers the question.
        # Left as a documented no-op for this PDF corpus rather than
        # "fixed" into a regression.
        versioned = [r for r in results if r.get("sdk_version") == version]
        if not versioned:
            return f"No chunks found specifically for version {version}.", []
        chunks = []
        for i, r in enumerate(versioned[:5], 1):
            chunks.append(
                f"--- {r['source_doc']}, page {r['page_number']} ---\n{r['text'][:500]}"
            )
        return f"Documentation for {version}:\n\n" + "\n\n".join(chunks), versioned[:5]

    elif tool_name == "compare_versions":
        query = args.get("query") or "differences between versions"
        # Prefer the two api_version strings actually named in the query
        # over hard-coded "v2"/"v3" suffixes — the latter only helps the
        # Swagger corpus (whose docs literally say "v2"/"v3") and actively
        # misleads GitHub-style comparisons (2022-11-28 vs 2025-06-01,
        # neither of which contains the text "v2" or "v3" at all).
        detected = list(dict.fromkeys(_extract_versions(query)))
        if len(detected) >= 2:
            v_a, v_b = detected[0], detected[-1]
        else:
            v_a, v_b = "v2", "v3"
        results_v2 = store.search(f"{query} {v_a}", top_k=4)
        results_v3 = store.search(f"{query} {v_b}", top_k=4)

        parts = [f"=== {v_a} ==="]
        for r in results_v2[:3]:
            parts.append(f"[{r['source_doc']}] {r['text'][:400]}")
        parts.append(f"\n=== {v_b} ===")
        for r in results_v3[:3]:
            parts.append(f"[{r['source_doc']}] {r['text'][:400]}")
        return "\n".join(parts), (results_v2[:3] + results_v3[:3])

    elif tool_name == "get_error_info":
        code = args.get("code", "")
        query = args.get("query") or f"error {code} HTTP"
        results = store.search(query, top_k=5)
        if not results:
            return f"No error information found for code {code}.", []
        chunks = []
        for r in results[:3]:
            text = r["text"]
            if code and code in text:
                chunks.append(f"[MATCH] {r['source_doc']}:\n{text[:500]}")
            else:
                chunks.append(f"[PARTIAL] {r['source_doc']}:\n{text[:300]}")
        return f"Error information for code {code}:\n\n" + "\n\n".join(chunks), results[:3]

    elif tool_name == "get_parameter_default":
        param = args.get("param", "")
        query = args.get("query") or f"parameter {param} default"
        results = store.search(query, top_k=6)
        if not results:
            return f"No parameter information found for {param}.", []
        chunks = []
        for r in results[:4]:
            if param.lower() in r["text"].lower():
                chunks.append(f"[EXACT] {r['source_doc']}:\n{r['text'][:500]}")
            else:
                chunks.append(f"[PARTIAL] {r['source_doc']}:\n{r['text'][:300]}")
        return f"Parameter info for {param}:\n\n" + "\n\n".join(chunks), results[:4]

    elif tool_name == "check_deprecation":
        subject = args.get("subject", "")
        api_version = args.get("api_version", "")
        api_version = getattr(api_version, "value", api_version)  # Enum -> plain str
        query = f"{subject} {api_version}"
        results = store.search(query, top_k=8)
        if not results:
            return (f"No changelog information found for '{subject}' "
                     f"at version {api_version}."), []
        # A real "deprecated" label is rare in raw API docs; what actually
        # signals a removal/replacement is comparative/changelog language
        # around the subject — that's what this tool looks for.
        change_markers = (
            "no longer", "removed", "replaced", "deprecated", "instead of",
            "did not exist", "requires a follow-up", "undocumented",
            "new in", "added in", "introduced in", "no way to", "heuristic",
            "override", "now be specified", "can be pre-armed",
        )
        hits = []
        for r in results:
            text = r["text"]
            if subject.lower() in text.lower() and any(
                m in text.lower() for m in change_markers
            ):
                hits.append(f"[CHANGED @ {api_version}] {r['source_doc']}:\n{text[:500]}")
        if not hits:
            for r in results[:3]:
                hits.append(f"[CONTEXT] {r['source_doc']}:\n{r['text'][:400]}")
        return (f"Deprecation/replacement check for '{subject}' at "
                f"{api_version}:\n\n" + "\n\n".join(hits)), results[:5]

    elif tool_name == "finish":
        return args.get("answer", "No answer provided."), []

    return f"Unknown tool: {tool_name}", []


# ---------------------------------------------------------------------------
# Chain of Thought — ask the LLM to reason about the next step
# ---------------------------------------------------------------------------

def _parse_agent_output(text):
    """Extract JSON from the LLM response, handling markdown code blocks."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object in the text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _call_llm(system_prompt, messages):
    """Call the Groq LLM for agent reasoning."""
    if not settings.GROQ_API_KEY:
        # Fallback: no LLM available, return a simple search+finish plan
        return None

    from rag_core.generators import _post_groq_with_retry  # shares 429 retry logic

    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        # Deterministic: this call must produce one strict JSON
        # object, not creative prose — temperature 0.1 was still
        # enough sampling variance to occasionally break format.
        "temperature": 0,
        # The loop's own "finish" answer text is no longer load-bearing —
        # run_agent delegates the real answer to _synthesize_answer via the
        # shared generator once real tool context exists (see its
        # docstring) — so this call only ever needs to carry a short
        # thought + tool + args (RULES #8), not a full essay. 400
        # comfortably covers that while using a fraction of the tokens/min
        # budget a free-tier Groq key enforces (observed: 8000 TPM), which
        # matters because this call happens once per agent step.
        "max_tokens": 400,
        "top_p": 0.9,
    }
    try:
        message = _post_groq_with_retry(payload)
        content = (message.get("content") or "").strip()
        if content:
            return content
        # Some reasoning models served via Groq (e.g. openai/gpt-oss-*) put
        # their ENTIRE output, including the final JSON tool call, into a
        # separate "reasoning" field and leave "content" empty for anything
        # non-trivial — observed directly against this model/key: a "Say OK"
        # prompt returns content="OK", but the strict tool-call JSON this
        # loop asks for often comes back with content="" and the real
        # {"thought":...,"tool":...} JSON sitting inside "reasoning" instead.
        # Fall back to it rather than discarding a real, valid tool call as
        # if the model produced nothing (_parse_agent_output already knows
        # how to pull a {...} JSON object out of surrounding prose).
        return (message.get("reasoning") or "").strip() or None
    except Exception:
        return None


_VERSION_RE = re.compile(r"2022-11-28|2025-06-01|\b2\.x\b|\b3\.x\b")
_SNAKE_CASE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_CAMEL_CASE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:[A-Z][a-z0-9]*)+\b")
_CHANGE_MARKERS = (
    "no longer", "removed", "replaced", "did not exist", "requires a "
    "follow-up", "undocumented", "heuristic", "no way to", "instead",
    "new in", "added in", "introduced",
)


def _extract_versions(question):
    """Api versions named in the question, in the order they appear."""
    return _VERSION_RE.findall(question)


# Fixed chronological/semantic ranking within each version family — used
# instead of "whichever version the question happens to name last", since
# question phrasing isn't consistent about that ("X replaces the heuristic
# used in <old version>" names the *old* version last).
_VERSION_RANK = {"2022-11-28": 0, "2025-06-01": 1, "2.x": 0, "3.x": 1}


def _pick_target_version(versions):
    """The newer/target version among the ones named in the question."""
    if not versions:
        return None
    return max(dict.fromkeys(versions), key=lambda v: _VERSION_RANK.get(v, 0))


_NAMED_FIELD_RE = re.compile(
    r"\bthe ([a-z][a-z0-9_]{2,30}) (?:parameter|field|flag|option|key|syntax)\b",
    re.IGNORECASE,
)


def _extract_subject(question):
    """Best-effort guess at the specific endpoint/parameter/flag the
    question is about: prefer an unambiguous identifier-looking token
    (snake_case or camelCase, e.g. 'make_latest'), then fall back to a
    plain word explicitly called out as "the X parameter/field/..."
    (e.g. 'context' in "the context parameter format changed")."""
    m = (
        _SNAKE_CASE_RE.search(question)
        or _CAMEL_CASE_RE.search(question)
        or _NAMED_FIELD_RE.search(question)
    )
    return m.group(1) if m and m.re is _NAMED_FIELD_RE else (m.group() if m else None)


def _fallback_plan(question, step, context_results):
    """Deterministic fallback when no LLM is available.

    Still a genuinely *conditional* plan, not a fixed script: whether step 2
    reaches for check_deprecation depends on (a) the question naming a
    specific api_version and subject, and (b) step 1's own retrieved text
    actually containing change/replacement language for that version — i.e.
    step 3 depends on what step 2 found, the same dependency the LLM-driven
    branch above is free to discover on its own.
    """
    versions = _extract_versions(question)
    subject = _extract_subject(question)

    if step == 0:
        return {
            "thought": "I'll search the documentation for information about this question.",
            "tool": "search_docs",
            "args": {"query": question},
        }

    if step == 1:
        distinct_versions = list(dict.fromkeys(versions))
        if distinct_versions:
            target_version = _pick_target_version(distinct_versions)
            return {
                "thought": f"The question names api_version {target_version}; "
                           f"pulling docs scoped to that version to see what "
                           f"actually changed there.",
                "tool": "get_version_info",
                "args": {"version": target_version, "query": question},
            }
        return {
            "thought": "No specific version named in the question; broadening the search.",
            "tool": "search_docs",
            "args": {"query": question + " default parameter"},
        }

    if step == 2 and versions and subject:
        combined_text = " ".join(r.get("text", "") for r in context_results).lower()
        if any(marker in combined_text for marker in _CHANGE_MARKERS):
            target_version = _pick_target_version(versions)
            return {
                "thought": f"Step 2's retrieval shows '{subject}' changed for "
                           f"{target_version} — checking check_deprecation for "
                           f"what replaced it before answering.",
                "tool": "check_deprecation",
                "args": {"subject": subject, "api_version": target_version},
            }

    # Nothing more to branch on: finish with what we have.
    return {
        "thought": "I have gathered enough information from the documentation.",
        "tool": "finish",
        "args": {"answer": _synthesize_answer(question, context_results)},
    }


def _synthesize_answer(question, context_results):
    """Generate a clean grounded answer from accumulated retrieval results.

    context_results is a list of real result dicts (chunk_id/source_doc/
    page_number/score/text) gathered across the agent's steps — not
    formatted display strings — so the generator sees genuine prose and
    keeps real citations, instead of extracting fragments of the
    "--- Chunk N: file, page P (score: X) ---" debug header as if it were
    document text.

    Deliberately routes through the SAME generator the fixed workflow uses
    (settings.DEFAULT_GENERATOR, e.g. Groq) when one is configured, rather
    than trusting the agent loop's own inline "answer" text. The loop's
    terse ReAct system prompt is tuned for reliable tool-call JSON, not
    prose composition — the specialized prompt in generate_groq (refusal
    rules, citation/formatting guidance) is what the workflow's answers
    benefit from, and the assignment's "same model" requirement means the
    agent's answers should get the same treatment. The agent's own job is
    which context to gather; final-answer quality is kept consistent
    between both systems here, not a second axis they're scored on.
    """
    if not context_results:
        return "I could not find the answer in the provided documents."

    # De-dupe by chunk_id (the same chunk can surface across multiple
    # searches) while preserving first-seen order.
    seen_ids = set()
    deduped = []
    for r in context_results:
        cid = r.get("chunk_id")
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        deduped.append(r)

    from rag_core.generators import GENERATORS, generate_extractive

    if settings.GROQ_API_KEY and settings.DEFAULT_GENERATOR in GENERATORS:
        gen = GENERATORS[settings.DEFAULT_GENERATOR](question, deduped)
        if not gen.get("error") and not gen["refused"]:
            return gen["answer"]

    # No LLM configured (or it errored/refused): deterministic extractive
    # fallback, same as before.
    pseudo_results = [{**r, "lexical_overlap": 1.0, "heading_overlap": 0.0} for r in deduped]
    gen = generate_extractive(question, pseudo_results)
    if not gen["refused"] and gen["answer"] != "I could not find the answer in the provided documents.":
        return gen["answer"]

    # Fallback: simple extraction from concatenated context text
    all_text = " ".join(r.get("text", "") for r in context_results)
    q_lower = question.lower()
    q_terms = {
        t for t in re.findall(r"[a-z0-9_.]+", q_lower)
        if len(t) > 2 and t not in {"what", "how", "which", "when", "where",
                                      "does", "the", "this", "that", "with"}
    }

    sentences = re.split(r"(?<=[.!?])\s+", all_text)
    scored = []
    for sent in sentences:
        sent_lower = sent.lower()
        overlap = sum(1 for t in q_terms if t in sent_lower)
        has_number = bool(re.search(r"\d", sent))
        asks_number = bool(re.search(r"default|value|how many", q_lower))
        score = overlap + (0.5 if has_number and asks_number else 0)
        if score > 0:
            scored.append((score, sent.strip()))

    if not scored:
        first = (context_results[0].get("text", ""))[:400]
        return first if first else "I could not find the answer in the provided documents."

    scored.sort(key=lambda x: -x[0])
    seen = set()
    parts = []
    for _, sent in scored[:3]:
        canonical = sent.lower()[:50]
        if canonical not in seen:
            seen.add(canonical)
            parts.append(sent)

    if len(parts) > 1:
        return "\n".join(f"- {p}" for p in parts)
    return parts[0] if parts else (context_results[0].get("text", ""))[:400]


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def run_agent(question, store, max_steps=5, time_budget=30,
              max_tokens=6000, max_cost_usd=0.01):
    """Run the ReAct agent loop.

    Returns:
        {
            "answer": str,
            "steps": [{"step": int, "thought": str, "tool": str,
                       "args": dict, "observation": str}],
            "metrics": {
                "latency_ms": float,
                "api_calls": int,
                "tools_used": [str],
                "steps_taken": int,
                "stopped_by": str,  # "finished" | "max_steps" | "time_budget"
                                     # | "token_budget" | "cost_budget"
                                     # | "schema_error" | "parse_error"
                "est_tokens": int,
                "est_cost_usd": float,
            }
        }
    """
    t0 = time.perf_counter()
    steps = []
    context_results = []
    tools_used = set()
    llm_available = bool(settings.GROQ_API_KEY)
    system_prompt = _build_system_prompt() if llm_available else ""
    conversation = []
    stopped_by = "finished"
    est_tokens_used = estimate_tokens(system_prompt)
    consecutive_schema_failures = 0
    answer = None

    for step_num in range(max_steps):
        # --- Check time budget ---
        elapsed = time.perf_counter() - t0
        if elapsed > time_budget:
            stopped_by = "time_budget"
            break

        # --- Circuit breaker: cumulative token/cost budget. Cost is only
        # meaningful when steps are actually making LLM calls; in fallback
        # mode (no API key) the loop is deterministic and genuinely free, so
        # only the token-volume cap applies. ---
        if est_tokens_used > max_tokens:
            stopped_by = "token_budget"
            break
        if llm_available and estimate_cost_usd(est_tokens_used, 0) > max_cost_usd:
            stopped_by = "cost_budget"
            break

        # --- THOUGHT + ACTION: Get the next step ---
        if llm_available:
            if not conversation:
                conversation.append({
                    "role": "user",
                    "content": f"Question: {question}\n\n"
                               f"Start by deciding which tool to use first.",
                })
            raw = _call_llm(system_prompt, conversation)
            est_tokens_used += estimate_tokens(raw or "")
            if raw:
                parsed = _parse_agent_output(raw)
            else:
                parsed = _fallback_plan(question, step_num, context_results)
        else:
            parsed = _fallback_plan(question, step_num, context_results)

        if not parsed:
            stopped_by = "parse_error"
            break

        thought = parsed.get("thought", "")
        tool = parsed.get("tool", "finish")
        args = parsed.get("args", {})
        est_tokens_used += estimate_tokens(thought) + estimate_tokens(json.dumps(args))

        # --- Validate args against the tool's strict schema (Week 7:
        # circuit breaker against malformed/execution-time-failing calls) ---
        ok, cleaned_or_error = _validate_tool_args(tool, args)
        if not ok:
            consecutive_schema_failures += 1
            observation = f"Tool call rejected: {cleaned_or_error}"
            steps.append({
                "step": step_num + 1,
                "thought": thought,
                "tool": tool,
                "args": args,
                "observation": observation,
            })
            if consecutive_schema_failures >= 2:
                stopped_by = "schema_error"
                answer = _synthesize_answer(question, context_results)
                break
            if llm_available:
                conversation.append({"role": "assistant", "content": raw})
                conversation.append({
                    "role": "user",
                    "content": f"Observation:\n{observation}\n\nNow decide the next step.",
                })
            continue
        consecutive_schema_failures = 0
        args = cleaned_or_error

        # --- EXECUTE the tool ---
        observation, raw_results = _execute_tool(tool, args, store)
        est_tokens_used += estimate_tokens(observation)
        tools_used.add(tool)

        step_record = {
            "step": step_num + 1,
            "thought": thought,
            "tool": tool,
            "args": args,
            "observation": observation[:800],  # cap for display
        }
        steps.append(step_record)

        # Accumulate real retrieval results for answer synthesis (not the
        # formatted display string — see _execute_tool's docstring).
        if tool != "finish":
            context_results.extend(raw_results)

        # --- Check if agent decided to finish ---
        if tool == "finish":
            stopped_by = "finished"
            # Prefer the shared synthesis path (same generator the workflow
            # uses) over the loop-model's own inline "answer" text whenever
            # real tool context was actually gathered — see
            # _synthesize_answer's docstring for why. Fall back to the
            # model's own answer only when nothing was ever retrieved.
            answer = (_synthesize_answer(question, context_results)
                      if context_results else args.get("answer", observation))
            break

        # --- Update conversation for next LLM call ---
        if llm_available:
            conversation.append({"role": "assistant", "content": raw})
            conversation.append({
                "role": "user",
                "content": f"Observation:\n{observation[:1000]}\n\n"
                           f"Now decide the next step.",
            })
    else:
        # Exhausted max steps — force a finish
        stopped_by = "max_steps"
        answer = _synthesize_answer(question, context_results)
        steps.append({
            "step": len(steps) + 1,
            "thought": "Reached maximum steps — synthesizing answer from gathered context.",
            "tool": "finish",
            "args": {"answer": answer},
            "observation": answer[:800],
        })

    t1 = time.perf_counter()
    latency_ms = round((t1 - t0) * 1000, 1)

    if answer is None:
        answer = _synthesize_answer(question, context_results)

    # Cost is genuinely $0 when no LLM call was ever made (fallback/
    # deterministic mode) - not an approximation gap to paper over.
    est_cost_usd = estimate_cost_usd(est_tokens_used, estimate_tokens(answer)) \
        if llm_available else 0.0

    return {
        "answer": answer,
        "steps": steps,
        "metrics": {
            "latency_ms": latency_ms,
            "api_calls": sum(1 for s in steps if s["tool"] != "finish"),
            "tools_used": sorted(tools_used),
            "steps_taken": len(steps),
            "stopped_by": stopped_by,
            "est_tokens": est_tokens_used,
            "est_cost_usd": est_cost_usd,
        },
    }
