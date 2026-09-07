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


def _split_long_paragraph(para, chunk_size, chunk_overlap):
    """Word-align a paragraph too long to fit in one chunk into ~chunk_size
    windows, carrying chunk_overlap worth of trailing words into the next
    window - the same word-window strategy used for normal chunk packing.

    Needed because PDF text extraction often drops blank lines entirely, so a
    whole page can come back as a single "paragraph". Without this, that
    paragraph used to be kept as one oversized chunk mixing every section on
    the page (a "Styles and Themes" tail bleeding into a "Jetpack Compose"
    chunk, for example) instead of being split like any other long content.
    """
    words = para.split(" ")
    pieces = []
    start = 0
    while start < len(words):
        end = start
        length = 0
        while end < len(words) and (length + len(words[end]) + 1) <= chunk_size:
            length += len(words[end]) + 1
            end += 1
        if end == start:
            end = start + 1  # a single word longer than chunk_size - take it anyway
        pieces.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        back, back_len = end, 0
        while back > start and back_len < chunk_overlap:
            back -= 1
            back_len += len(words[back]) + 1
        start = max(back, start + 1)
    return pieces


def chunk_page_text(text, chunk_size, chunk_overlap):
    raw_paragraphs = _paragraphs(text)
    if not raw_paragraphs:
        return []

    paragraphs = []
    for para in raw_paragraphs:
        if len(para) > chunk_size:
            paragraphs.extend(_split_long_paragraph(para, chunk_size, chunk_overlap))
        else:
            paragraphs.append(para)

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
