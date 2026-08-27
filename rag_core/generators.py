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


# ----------------------------------------------------------------- groq ----

PROMPT_TEMPLATE = """You are a developer-documentation assistant.

Answer the user's question using ONLY the numbered context chunks below.

Rules:
1. Cite the chunk you used as [chunk_id] right after the claim.
2. If the context does not contain the answer, reply with exactly one
   sentence: "{refusal}"
3. Do not make up parameter names, defaults or code.
4. Keep the answer short: 4 to 5 lines maximum.

Context chunks:
{context}

User question:
{question}

Answer:"""


def build_context(results):
    blocks = []
    for r in results:
        blocks.append(
            f"[{r['chunk_id']}] ({r['source_doc']} p{r['page_number']})\n{r['text']}"
        )
    return "\n\n".join(blocks)


def generate_groq(question, results):
    params = {"temperature": 0.0, "max_tokens": 300}

    if not results:
        return {"answer": _REFUSAL, "model": settings.GROQ_MODEL,
                "prompt_version": settings.PROMPT_VERSION_LLM,
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
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 300,
            },
            timeout=settings.GROQ_TIMEOUT,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.RequestException as e:
        return {"answer": f"Generator error: {e}", "model": settings.GROQ_MODEL,
                "prompt_version": settings.PROMPT_VERSION_LLM,
                "params": params, "refused": False,
                "error": type(e).__name__}

    refused = _REFUSAL.lower() in answer.lower()
    return {"answer": answer, "model": settings.GROQ_MODEL,
            "prompt_version": settings.PROMPT_VERSION_LLM,
            "params": params, "refused": refused}


# ------------------------------------------------------------ extractive ----


def generate_extractive(question, results):
    q_terms = _terms(question)

    best = []  # (overlap_score, rank, sent_idx, sentence, result)
    for r in results:
        for i, sent in enumerate(_sentences(r["text"])):
            overlap = len(q_terms & _terms(sent))
            if overlap <= 0:
                continue
            # prefer more term overlap, then earlier sentences in better ranks
            score = (overlap / max(1, len(q_terms)) ** 0.5) - 0.01 * i \
                    - 0.001 * r["rank"]
            best.append((score, r["rank"], i, sent, r))

    if not best:
        return {"answer": _REFUSAL, "model": "extractive-v1",
                "prompt_version": settings.PROMPT_VERSION_EXTRACTIVE,
                "params": {"max_sentences": 2}, "refused": True}

    best.sort(key=lambda t: (-t[0], t[1], t[2]))

    picked, used_chunks = [], set()
    for _, _, _, sent, r in best:
        if r["chunk_id"] in used_chunks and len(picked) >= 1:
            continue
        picked.append((sent, r))
        used_chunks.add(r["chunk_id"])
        if len(picked) == 2:
            break

    parts = []
    cited = []
    for sent, r in picked:
        parts.append(f"{sent} [{r['chunk_id']}]")
        if r["chunk_id"] not in cited:
            cited.append(r["chunk_id"])

    return {"answer": " ".join(parts), "model": "extractive-v1",
            "prompt_version": settings.PROMPT_VERSION_EXTRACTIVE,
            "params": {"max_sentences": 2},
            "refused": False}


GENERATORS = {
    "groq": generate_groq,
    "extractive": generate_extractive,
}
