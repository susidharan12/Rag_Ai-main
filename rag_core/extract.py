"""Turn an uploaded file into a list of {"text", "page_number"} page dicts."""

import io
import os
import re


def _pdf_pages_from_bytes(data):
    try:
        import pypdf as _pypdf_reader_lib
    except ImportError:
        _pypdf_reader_lib = None

    import PyPDF2

    pages = []
    reader = PyPDF2.PdfReader(io.BytesIO(data))
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip() and len(text.strip()) < 20:
            text = _ocr_fallback(data, i, text)
        pages.append({"text": text, "page_number": i + 1})
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
