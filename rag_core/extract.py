"""Turn an uploaded file into a list of {"text", "page_number"} page dicts."""

import io
import os
import re


def _clean_pdf_text(text):
    """Undo common PDF text-extraction spacing artifacts - many PDF fonts/
    encodings make the extractor emit a stray space before a hyphen or a
    comma (e.g. "AI -powered", "third -party", "PostgreSQL ,"), which reads
    as visibly broken once it lands in an answer. Line-wrap hyphenation
    ("cross-\\nfunctional") is untouched since it has no such leading space.
    """
    # Require >=2 lowercase letters after the hyphen so this only joins a
    # genuine compound word ("AI -powered" -> "AI-powered", "third -party"
    # -> "third-party") and never a CLI short flag ("curl -X", "POST -H",
    # "-d '{...}'") - those are always a single letter after the hyphen and
    # would otherwise get wrongly glued onto the preceding word
    # ("curl -X" -> "curl-X"), which then reads as one unbroken token.
    text = re.sub(r"(?<=\w) -(?=[a-z]{2,})", "-", text)
    # Mid-word line-wrap hyphenation ("speci-\nfying") reads as broken text
    # once the newline is later collapsed to a space ("speci- fying"); join
    # it back into one word. A real end-of-line hyphenated compound is rare
    # enough here (reference/API docs, not prose) that this heuristic is
    # safe - it only fires when a lowercase letter directly follows.
    text = re.sub(r"(\w)-\n(?=[a-z])", r"\1", text)
    text = re.sub(r"[ \t]+([,.;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def _pdf_pages_from_bytes(data):
    pages = _pymupdf_pages(data)
    if pages is None:
        pages = _pypdf2_pages(data)
    return pages


def _pymupdf_pages(data):
    """Preferred extractor - PyMuPDF preserves inter-word spacing that
    PyPDF2 silently drops on some PDF fonts/encodings (e.g. "the java
    client generator" comes back as "thejavaclientgenerator" from PyPDF2 on
    the same file), which otherwise poisons every downstream chunk/answer.
    Returns None if pymupdf isn't installed so callers fall back to PyPDF2.
    """
    try:
        import pymupdf
    except ImportError:
        return None

    pages = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            text = page.get_text() or ""
            if text.strip() and len(text.strip()) < 20:
                text = _ocr_fallback(data, i, text)
            pages.append({"text": _clean_pdf_text(text), "page_number": i + 1})
    return pages


def _pypdf2_pages(data):
    import PyPDF2

    pages = []
    reader = PyPDF2.PdfReader(io.BytesIO(data))
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip() and len(text.strip()) < 20:
            text = _ocr_fallback(data, i, text)
        pages.append({"text": _clean_pdf_text(text), "page_number": i + 1})
    return pages


def _ocr_fallback(data, page_index, existing_text):
    """OCR a scanned page with pymupdf+tesseract if both are available.

    Optional on purpose: the Week 5 machine has neither installed, and every
    PDF used so far has a real text layer.
    """

    try:
        import pymupdf
        import pytesseract
    except ImportError:
        return existing_text

    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            pix = doc[page_index].get_pixmap(dpi=200)
            tmp = os.path.join(
                os.environ.get("TEMP", "."), f"_ocr_{os.getpid()}_{page_index}.png"
            )
            pix.save(tmp)
            try:
                return pytesseract.image_to_string(tmp, lang="eng") or ""
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
    except Exception:
        return existing_text


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _split_frontmatter(text):
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, text[match.end():]


def extract_pages(file_name, data):
    """Return (frontmatter_meta, pages) for pdf/md/txt uploads."""

    lower = file_name.lower()

    if lower.endswith(".pdf"):
        return {}, _pdf_pages_from_bytes(data)

    raw = data.decode("utf-8", errors="replace")
    meta, body = _split_frontmatter(raw)

    if lower.endswith((".md", ".markdown")):
        # Split markdown on headings so one "page" == one top-level section.
        parts = re.split(r"\n(?=#{1,2} )", body)
        pages = []
        for i, part in enumerate(parts):
            if part.strip():
                title = part.lstrip("#").splitlines()[0].strip()
                pages.append({"text": part.strip(), "page_number": i + 1,
                              "section": title})
        if not pages:
            pages = [{"text": body, "page_number": 1}]
        return meta, pages

    lines = body.splitlines()
    per = 40
    pages = [
        {"text": "\n".join(lines[i:i + per]).strip(), "page_number": i // per + 1}
        for i in range(0, len(lines), per)
        if "\n".join(lines[i:i + per]).strip()
    ] or [{"text": body, "page_number": 1}]
    return meta, pages
