"""Word-aligned chunker.

Same algorithm as the Week 3 pdf_reader.chunk_page_text (word windows of
roughly CHUNK_SIZE characters with CHUNK_OVERLAP carried across the
boundary), re-implemented here so rag_core has zero imports from the legacy
pipeline.
"""

import re


def _paragraphs(text):
    blocks = re.split(r"\n\s*\n+", text.strip())
    cleaned = []
    for block in blocks:
        block = block.strip()
        if block:
            cleaned.append(block)
    return cleaned


def chunk_page_text(text, chunk_size, chunk_overlap):
    paragraphs = _paragraphs(text)
    if not paragraphs:
        return []

    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if not current:
            current = [para]
            current_len = para_len
            continue

        if current_len + 1 + para_len <= chunk_size:
            current.append(para)
            current_len += 1 + para_len
            continue

        chunks.append("\n\n".join(current))

        overlap_parts = []
        overlap_len = 0
        for p in reversed(current):
            p_len = len(p)
            overlap_parts.insert(0, p)
            overlap_len += p_len + 1
            if overlap_len >= chunk_overlap:
                break

        if para_len > chunk_size:
            # keep a very long paragraph as a single chunk candidate to avoid
            # splitting a full code block or heading paragraph in half.
            current = [para]
            current_len = para_len
        else:
            # Carry the overlap forward into the next chunk
            current = overlap_parts + [para]
            current_len = overlap_len + 1 + para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def chunk_pages(pages, chunk_size, chunk_overlap):
    """Yield (chunk_text, metadata) for every page dict."""

    out = []
    for page in pages:
        text = page.get("text") or ""
        if not text.strip():
            continue
        for idx, chunk in enumerate(chunk_page_text(text, chunk_size, chunk_overlap)):
            meta = {
                "page_number": page.get("page_number", 1),
                "chunk_index": idx,
                "section": page.get("section", ""),
            }
            for key in ("sdk_version", "doc_title"):
                if key in page:
                    meta[key] = page[key]
            out.append((chunk, meta))
    return out
