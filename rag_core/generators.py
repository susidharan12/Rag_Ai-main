"""Answer generators.

Two interchangeable backends behind one interface:

  generate_groq        — Groq cloud LLM (OpenAI-compatible API) with the
                         strict grounded/refuse prompt.
  generate_extractive  — deterministic no-LLM fallback: picks the highest
                         query-term-overlap sentences from retrieved chunks.
                         Used when the Groq API is unreachable or no key is
                         configured (it also makes trace replay bit-for-bit
                         reproducible).

Both return {"answer": str, "model": str, "prompt_version": str,
             "params": dict, "refused": bool}.
"""

import re

import requests

from rag_core import settings

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "in", "on", "for",
    "to", "and", "or", "what", "which", "who", "whom", "how", "does", "do",
    "did", "can", "could", "should", "would", "when", "where", "why", "with",
    "by", "at", "from", "as", "be", "been", "it", "its", "this", "that",
    "these", "those", "there", "their", "them", "they", "i", "you", "we",
    "my", "your", "our", "me", "us", "not", "no", "yes",
}

_REFUSAL = "I could not find the answer in the provided documents."


def _terms(text):
    return {t for t in re.findall(r"[a-z0-9_.]+", text.lower())
            if t not in _STOPWORDS and len(t) > 1}


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [s.strip() for s in parts if s.strip()]


def _candidates(text):
    """Yield answer candidates as (sentence, single_table_row).

    Table rows are split on '|' so a parameter/error row can be selected and
    returned on its own instead of dragging a whole table blob into the answer
    (Week 5 M6: fact buried in a table/list dump).
    """
    cands = []
    for sent in _sentences(text):
        if "|" in sent:
            for cell in sent.split("|"):
                cell = cell.strip()
                if cell and len(cell) > 1:
                    cands.append(cell)
        else:
            cands.append(sent)
    return cands


# ----------------------------------------------------------------- groq ----

PROMPT_TEMPLATE = """You are a knowledgeable and helpful documentation assistant. Your job is to provide clear, accurate, and comprehensive answers based on the documentation provided below.

Instructions:
1. Answer the user's question using the context chunks below as your source of truth.
2. Synthesize information from multiple chunks when needed to give a complete answer.
3. Provide clear, well-structured explanations — use bullet points, numbered lists, or paragraphs as appropriate.
4. If the context contains relevant information, use it to give a thorough answer. Do NOT refuse unless the context is completely unrelated to the question.
5. Only say "I could not find the answer in the provided documents" if the context has absolutely no relevant information.
6. Do not fabricate parameter names, default values, or code examples — only use what is explicitly stated in the context.
7. Use a natural, conversational tone. Be helpful and informative like a senior developer explaining documentation.
8. If the answer requires multiple facts from different chunks, combine them into a cohesive response.

Context chunks:
{context}

User question:
{question}

Answer:"""


def build_context(results):
    blocks = []
    for i, r in enumerate(results, 1):
        source = r.get('source_doc', 'unknown')
        page = r.get('page_number', '?')
        version = r.get('sdk_version', '')
        version_tag = f" [{version}]" if version else ""
        blocks.append(
            f"--- Source {i}: {source}, page {page}{version_tag} ---\n{r['text']}"
        )
    return "\n\n".join(blocks)


def generate_groq(question, results):
    params = {"temperature": 0.2, "max_tokens": 1024}

    if not results:
        return {"answer": _REFUSAL, "model": settings.GROQ_MODEL,
                "prompt_version": settings.PROMPT_VERSION,
                "params": params, "refused": True}

    prompt = PROMPT_TEMPLATE.format(
        refusal=_REFUSAL, context=build_context(results), question=question
    )
    try:
        response = requests.post(
            settings.GROQ_URL,
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": settings.GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a helpful, accurate, and thorough documentation assistant. Always provide complete answers based on the provided context."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 1024,
                "top_p": 0.9,
            },
            timeout=settings.GROQ_TIMEOUT,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.RequestException as e:
        return {"answer": f"Generator error: {e}", "model": settings.GROQ_MODEL,
                "prompt_version": settings.PROMPT_VERSION,
                "params": params, "refused": False,
                "error": type(e).__name__}

    answer = _clean_answer(answer)
    refused = _REFUSAL.lower() in answer.lower()
    return {"answer": answer, "model": settings.GROQ_MODEL,
            "prompt_version": settings.PROMPT_VERSION,
            "params": params, "refused": refused}


def _clean_answer(answer):
    """Clean up the answer text — remove citation artifacts and tidy formatting."""
    answer = answer.strip()
    # Remove citation tags like [chunk:pN:cN] or 【chunk:pN:cN】 if present
    cite = r"[A-Za-z0-9_\-]+(?::p\d+)?(?::c\d+)?"
    answer = re.sub(r"[【\[]\s*" + cite + r"\s*[】\]]?", "", answer)
    # Collapse double spaces
    answer = re.sub(r"[ \t]+", " ", answer)
    # Remove trailing dangling separators
    answer = re.sub(r"[ \t]+([,.;:])", r"\1", answer)
    # Strip raw chunk ids appended by extractive fallback
    answer = re.sub(r"\s+\[[A-Za-z0-9_\-:p.c]+\]\s*$", "", answer)
    return answer.rstrip().rstrip("。.,;:")


# ------------------------------------------------------------ extractive ----


def generate_extractive(question, results):
    """Deterministic, question-aware extractive reader.

    Unlike v1 (which returned the first 2 term-overlapping sentences, dragging
    whole table/list blobs into the answer), this version:

      * refuses when no retrieved chunk actually answers the question (M3) or
        when the top retrieval score is inside the embedding noise band;
      * extracts the specific field the question asks about (M4/M6) instead of
        quoting an entire row or table;
      * de-duplicates near-identical sentences (M5);
      * stops at a complete on-topic answer instead of drifting (M7).

    Still fully deterministic and replayable for the eval harness.
    """
    q_terms = _terms(question)
    asks_number = bool(re.search(r"\b(how many|what is the (default|maximum|"
                                 r"minimum)|what's the|how much|what value|"
                                 r"how big|limit|size|timeout|pool|how often|"
                                 r"how long)\b", question.lower()))

    if not results:
        return {"answer": _REFUSAL, "model": "extractive-v2",
                "prompt_version": settings.PROMPT_VERSION,
                "params": {"reason": "no_results"}, "refused": True}

    max_overlap = max((r.get("lexical_overlap", 0.0) for r in results), default=0.0)
    max_heading = max((r.get("heading_overlap", 0.0) for r in results), default=0.0)

    if max_overlap < 0.05 and max_heading < 0.05:
        return {"answer": _REFUSAL, "model": "extractive-v2",
                "prompt_version": settings.PROMPT_VERSION,
                "params": {"reason": "no_question_overlap",
                           "max_overlap": round(max_overlap, 3),
                           "max_heading": round(max_heading, 3)},
                "refused": True}

    top_score = max(r["score"] for r in results)

    # Relevance gate 1 (M3): if the question names a specific entity that is
    # not present anywhere in the retrieved context (e.g. "Go client",
    # "Kubernetes"), it is out of corpus - refuse before any extraction.
    anchor = _absent_anchor(question, results)
    if anchor:
        return {"answer": _REFUSAL, "model": "extractive-v2",
                "prompt_version": settings.PROMPT_VERSION,
                "params": {"reason": "anchor_absent",
                           "anchor": anchor},
                "refused": True}

    # Focused extraction: a parameter default or error-code row answers the
    # question directly and compactly (M4/M6) - no table blob to bury it.
    # This runs before the score gate so a genuinely answerable question whose
    # top similarity is near the noise floor (e.g. "what retries do I get on
    # send?" at 0.45) is still answered from the grounded row.
    focused = _focused_answer(question, results)
    if focused:
        ans, r = focused
        return {"answer": f"{ans} [{r['chunk_id']}]",
                "model": "extractive-v2",
                "prompt_version": settings.PROMPT_VERSION,
                "params": {"strategy": "focused",
                           "max_sentences": settings.EXTRACTIVE_MAX_SENTENCES},
                "refused": False}

    definition = _definition_answer(question, results)
    if definition:
        ans, r = definition
        return {"answer": ans,
                "model": "extractive-v2",
                "prompt_version": settings.PROMPT_VERSION,
                "params": {"strategy": "definition"},
                "refused": False}

    # Relevance gate 2: if no structured answer exists, the single highest
    # retrieval score must clear the embedding noise floor (M3).
    if top_score < settings.MIN_ANSWER_SCORE:
        return {"answer": _REFUSAL, "model": "extractive-v2",
                "prompt_version": settings.PROMPT_VERSION,
                "params": {"reason": "low_score",
                           "top_score": round(top_score, 4)},
                "refused": True}

    # Build scored candidates from every retrieved chunk.
    picked_terms = set()
    candidates = []
    for r in results:
        for cand in _candidates(r["text"]):
            c_terms = _terms(cand)
            shared = q_terms & c_terms
            if not shared:
                continue
            has_number = bool(re.search(r"\d", cand))
            qi = (len(shared) * 2.0
                  + (2.0 if has_number and asks_number else 0.0)
                  - 0.01 * len(cand)
                  + _candidate_rank(question, cand, r) * 4.0)
            candidates.append((qi, shared, cand, r))

    # Relevance gate 2: nothing on-topic in the retrieved context -> refuse (M3).
    if not candidates:
        return {"answer": _REFUSAL, "model": "extractive-v2",
                "prompt_version": settings.PROMPT_VERSION,
                "params": {"reason": "no_overlap"}, "refused": True}

    # Stable sort: reuse every content term only once, then fall back to the
    # highest-quality candidate so an answer is not starved of supporting text.
    candidates.sort(key=lambda t: (-t[0], t[3]["rank"]))
    picked = []
    used_chunks = set()
    for qi, shared, cand, r in candidates:
        new_terms = shared - picked_terms
        if new_terms:
            picked_terms |= shared
        if r["chunk_id"] in used_chunks and len(picked) >= 1:
            continue
        picked.append((cand, r))
        used_chunks.add(r["chunk_id"])
        if len(picked) >= settings.EXTRACTIVE_MAX_SENTENCES:
            break

    # Reject near-duplicate surface text (M5) before building the answer.
    final = []
    for cand, r in picked:
        if any(_similar(cand, other) for other, _ in final):
            continue
        final.append((cand, r))

    if not final:
        return {"answer": _REFUSAL, "model": "extractive-v2",
                "prompt_version": settings.PROMPT_VERSION,
                "params": {"reason": "all_duplicates"}, "refused": True}

    parts, cited = [], []
    for cand, r in final:
        parts.append(f"{cand} [{r['chunk_id']}]")
        if r["chunk_id"] not in cited:
            cited.append(r["chunk_id"])

    return {"answer": " ".join(parts), "model": "extractive-v2",
            "prompt_version": settings.PROMPT_VERSION,
            "params": {"max_sentences": settings.EXTRACTIVE_MAX_SENTENCES},
            "refused": False}


def _similar(a, b):
    """True if a and b are near-duplicate sentences (Week 5 M5)."""
    ta, tb = _canon(a), _canon(b)
    if not ta or not tb:
        return False
    inter = len(set(ta) & set(tb))
    return inter / min(len(ta), len(tb)) >= 0.6


def _canon(text):
    return text.lower().split()


# ---------------------------------------------------------------------------
# Focused structured extraction for parameter-table corpora (Week 5 M4/M6).
# The Nimbus SDK pages use `| param | type | default | required | desc |`
# markdown rows; this pulls the exact requested field instead of quoting the
# whole table and washing the answer out.
# ---------------------------------------------------------------------------


def _param_rows(text):
    """Return a dict of {param: (type, default, description)} parsed from
    markdown parameter-table rows embedded in a chunk."""
    out = {}
    # Rows are separated by a collapsed '| |' (the chunker flattened the table).
    for row in re.split(r"\|\s*\|", text):
        row = row.strip().strip("|")
        cells = [c.strip().strip("`") for c in row.split("|")]
        # A real data row: param | type | default | required | desc...
        if len(cells) >= 4 and re.fullmatch(r"[a-z_][a-z0-9_.]*", cells[0]):
            # Tables are 5 columns (param|type|default|required|description);
            # some are 4 columns with default in position 2 and the value text
            # directly after. Use the description column when present.
            if len(cells) >= 5 and cells[4].strip() and cells[4] not in ("yes", "no"):
                default_cell, desc_cell = cells[2], cells[4]
            else:
                default_cell, desc_cell = cells[2], cells[3]
            out[cells[0]] = (cells[1], default_cell, desc_cell)
    return out


def _find_parameter(question, results):
    """Answer a 'default/maximum value of PARAM' question directly. Returns a
    (answer_text, chunk) tuple, or None if no parameter row answers it."""
    low = question.lower()
    # Only fire the structured parameter lookup when the question is literally
    # asking for a value/default of a field ("what is the default X", "how many",
    # "which backoff", ...). "Which error code ..." is not a default question.
    if not re.search(r"\b(default|maximum|max|value|how many|how big|how much|"
                     r"retry|retries|backoff|timeout|scope|page size|interval|"
                     r"keepalive|pool|ttl|tolerance|expiry|limit)\b", low):
        return None
    # Map a question's intent to the parameter whose default is being asked for
    # (e.g. "how many times ... retry" -> max_retries; "backoff" ->
    # retry_backoff_ms), before falling back to a named token.
    intent_map = [
        (r"\bhow many times\b.*\bretry\b", "max_retries"),
        (r"\b(?:how many|number of|times).*retr(?:y|ies)", "max_retries"),
        (r"\bwhat\s+retries\b|\bhow many retries\b", "max_retries"),
        (r"\bbackoff\b", "retry_backoff_ms"),
        (r"\bretries\b", "max_retries"),
        (r"\bkeepalive\b|\binterval\b", "keepalive_ms"),
        (r"\bdefault\s+pool\b|\bpool\s+size\b|how big\b.*\bpool\b", "pool_size"),
        (r"\bpage size\b|\bhow many events\b|\bnone\b", "limit"),
        (r"\bscope\b", "scope"),
        (r"\bexpiry\b|\bttl\b|\btoken.*second", "ttl_seconds"),
        (r"\btimeout\b", "timeout_ms"),
        (r"\btolerance\b", "tolerance_seconds"),
    ]
    param = None
    for pattern, name in intent_map:
        if re.search(pattern, low):
            param = name
            break
    if not param:
        m = re.search(r"\b(retry_backoff_ms|timeout_ms|max_retries|pool_size|"
                      r"keepalive_ms|tolerance_seconds|ttl_seconds|scope|limit)\b",
                      low)
        if m:
            param = m.group(1)

    if not param:
        return None

    # Version-aware selection (M1/M2): for a versionless / v3-preferred
    # question, prefer the value from the current (v3) page; for an explicit
    # v2 question, prefer v2. Ties are broken toward the preferred version.
    from rag_core.store import _resolve_version_preference
    pref = _resolve_version_preference(question)

    def version_key(r):
        v = r.get("sdk_version", "")
        if not v:
            return 1
        if pref == "both":
            return 1
        if pref and v == pref:
            return 0
        return 2

    ordered = sorted(results, key=lambda r: (version_key(r), r["rank"]))
    for r in ordered:
        rows = _param_rows(r["text"])
        if param not in rows:
            continue
        ptype, default, desc = rows[param]
        if default in ("", "-", "None") and not desc:
            continue
        if re.search(r"maximum allowed value|max allowed|max value|how big", low):
            # Maximum-value questions want the upper bound, not the default
            # (e.g. limit max is 200, but its default is 50).
            nums = [int(n) for n in re.findall(r"\d+", desc + " " + default)]
            upper = max(nums) if nums else None
            if upper is not None:
                return f"{param} maximum allowed value is {upper}.", r
            val = desc.strip(" ,.;:") if default in ("", "-") else default
            return f"{param} max value: {val}.", r
        if default == "None":
            val = "None (optional, default no filter)" if "filter" in desc else "None"
            return f"{param} default is {val}.", r
        return f"{param} default is {default}.", r
    return None


def _find_error_retryable(question, results):
    """Answer 'is HTTP code N retryable?' directly from the errors table."""
    low = question.lower()
    code = None
    m = re.search(r"\b(400|401|403|429|500)\b", question)
    if m:
        code = m.group(1)
    if not code or "retryable" not in low:
        return None
    for r in results:
        for row in re.split(r"\|\s*\|", r["text"]):
            row = row.strip().strip("|")
            cells = [c.strip().strip("`") for c in row.split("|")]
            # errors-table row: NAME | http | retryable | meaning
            if len(cells) >= 4 and re.fullmatch(r"[A-Z_]{2,}", cells[0]):
                if cells[1] == code:
                    verdict = cells[2].strip()
                    return (f"HTTP {code} ({cells[0]}) is "
                            f"{'retryable' if verdict == 'yes' else 'not retryable'} "
                            f"per the error reference.", r)
                continue
    return None


def _focused_answer(question, results):
    """Try structured extraction first; return (answer, chunk) or None."""
    got = _find_parameter(question, results)
    if got:
        return got
    got = _find_error_retryable(question, results)
    if got:
        return got
    got = _find_support_status(question, results)
    if got:
        return got
    return None


def _find_support_status(question, results):
    """Answer 'is SDK v2 / <version> still supported?' from the maintenance-mode
    banner that appears in the versioned docs."""
    low = question.lower()
    if not re.search(r"\b(?:support|maintain|maintenance|still supported)\b", low):
        return None
    for r in results:
        text_lower = r["text"].lower()
        if "maintenance mode" in text_lower or \
           "no longer supported" in text_lower or \
           "still supported" in text_lower:
            # Prefer the most direct statement about support status.
            sent = None
            for s in _sentences(r["text"]):
                sl = s.lower()
                if ("maintenance" in sl or "supported" in sl) \
                        and ("v2" in sl or "sdk" in sl):
                    sent = s
                    break
            if sent is None:
                sent = r["text"][:120]
            return (f"Yes - {sent}", r)
    return None


_SENTENCE_START = {
    "what", "how", "which", "who", "whom", "where", "when", "why", "is", "are",
    "was", "were", "does", "do", "did", "can", "could", "should", "would",
    "for", "in", "on", "the", "a", "an", "according", "tell", "explain",
    "show", "in", "to", "of", "at", "with", "and", "or", "if", "per",
    "compare", "list", "name", "define", "give", "state", "describes",
}

_CORPUS_GENERIC_ANCHORS = {
    "nimbus", "sdk", "client", "docs", "sdk", "api", "gateway", "python",
    "error", "errors", "reference", "code", "codes", "parameter", "default",
    "example", "connect", "send", "event", "events", "endpoint",
}

# Concrete tech/domain terms that, if asked about but missing from the index,
# are a strong out-of-corpus signal (the docs only cover the Python Nimbus SDK).
_OOC_VOCAB = {
    "go", "kubernetes", "rust", "java", "node", "nodejs", "typescript",
    "curl", "dart", "swift", "ruby", "php", "stream", "websocket",
}


def _absent_anchor(question, results):
    """Return a specific entity the question names that is missing from every
    retrieved chunk (strong out-of-corpus signal), or None.

    A question like "retry backoff for the Nimbus SDK Go client" retrieves the
    topical Python send page at high similarity, but "Go" is nowhere in the
    index - a lexical contradiction the similarity score cannot see.
    """
    context = " ".join(r["text"] for r in results).lower()
    # underscored entities (RATE_LIMITED) must match their underscored form.
    context_norm = re.sub(r"[_'-]", "", context)
    qlow = question.lower()

    # CapWords entities and out-of-corpus vocabulary words.
    for tok in re.findall(r"[A-Z][A-Za-z][A-Za-z_-]{1,}", question):
        t = tok.lower()
        if t in _SENTENCE_START or t in _CORPUS_GENERIC_ANCHORS:
            continue
        flat = re.sub(r"[_'-]", "", t)
        if len(flat) <= 1:
            continue
        if re.search(r"\b" + re.escape(t) + r"\b", context) or \
           re.search(r"\b" + re.escape(flat) + r"\b", context_norm):
            continue
        # Multi-word anchors ("WebhookVerifier") may only match a leading stem.
        stem = re.split(r"[A-Z]", flat)[0]
        if len(stem) >= 5 and \
           re.search(r"\b" + re.escape(stem.lower()) + r"\b", context_norm):
            continue
        return tok

    for word in _OOC_VOCAB:
        if re.search(r"\b" + re.escape(word) + r"\b", qlow) and \
           not re.search(r"\b" + re.escape(word) + r"\b", context):
            return word
    return None


GENERATORS = {
    "groq": generate_groq,
    "extractive": generate_extractive,
}


def _heading_match_bonus(question, text):
    q = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
    if not q:
        return 0.0
    q_tokens = {t for t in q.split() if len(t) > 2 and t not in _STOPWORDS}
    if not q_tokens:
        return 0.0
    t = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    matches = sum(1 for tok in q_tokens if tok in t)
    return matches / max(len(q_tokens), 1)


def _candidate_rank(question, cand, result):
    base = 0.0
    base += _heading_match_bonus(question, result["text"])
    if re.search(r"\b" + re.escape(question.lower().strip()) + r"\b", result["text"].lower()):
        base += 0.25
    if re.search(r"\b" + re.escape(question.lower().strip()) + r"\b", (result.get("source_doc") or "").lower()):
        base += 0.1
    return base


def _definition_answer(question, results):
    """Handle 'what is X' / 'what are X' definitions from matching section text."""
    low = question.lower()
    if not re.search(r"\b(?:what is|what are|define|explain|tell me about)\b", low):
        return None

    q_norm = re.sub(r"[^a-z0-9]+", " ", low).strip()
    for r in results:
        text = r.get("text") or ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for i, line in enumerate(lines):
            norm = re.sub(r"[^a-z0-9]+", " ", line.lower()).strip()
            if not norm:
                continue
            if norm == q_norm:
                answer = " ".join(lines[max(0, i + 1): min(len(lines), i + 4)])
                if answer:
                    return (answer.strip(), r)
            phrase = q_norm.replace("what is ", "").replace("what are ", "").replace("define ", "").replace("explain ", "").strip()
            if phrase and (phrase in norm or norm in phrase):
                answer = " ".join(lines[max(0, i + 1): min(len(lines), i + 4)])
                if answer:
                    return (answer.strip(), r)
    return None
