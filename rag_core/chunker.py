"""Word-aligned chunker.

Same algorithm as the Week 3 pdf_reader.chunk_page_text (word windows of
roughly CHUNK_SIZE characters with CHUNK_OVERLAP carried across the
boundary), re-implemented here so rag_core has zero imports from the legacy
pipeline.
"""


def chunk_page_text(text, chunk_size, chunk_overlap):
    words = text.split()
    if not words:
        return []

    chunks = []
    current_words = []
    current_len = 0

    for word in words:
        current_words.append(word)
        current_len += len(word) + 1

        if current_len >= chunk_size:
            chunks.append(" ".join(current_words))

            overlap_words = []
            overlap_len = 0
            for w in reversed(current_words):
                overlap_len += len(w) + 1
                overlap_words.insert(0, w)
                if overlap_len >= chunk_overlap:
                    break

            current_words = overlap_words
            current_len = overlap_len

    if current_words and (not chunks or " ".join(current_words) != chunks[-1]):
        chunks.append(" ".join(current_words))

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
