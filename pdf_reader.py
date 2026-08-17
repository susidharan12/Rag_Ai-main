import os
import sys
import pickle

import faiss
import numpy as np
import PyPDF2
import pymupdf
import pytesseract
from sentence_transformers import SentenceTransformer

import config

pytesseract.pytesseract.tesseract_cmd = config.resolve_tesseract_cmd()

_embedding_model = None


def get_embedding_model():

    global _embedding_model

    if _embedding_model is None:

        print("Loading embedding model...")

        _embedding_model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)

        print("Embedding model loaded")

    return _embedding_model


def load_ocr_cache():

    if os.path.exists(config.OCR_CACHE_PATH):

        with open(config.OCR_CACHE_PATH, "rb") as f:
            return pickle.load(f)

    return {}


def save_ocr_cache(cache):

    with open(config.OCR_CACHE_PATH, "wb") as f:
        pickle.dump(cache, f)


def extract_page_text(pdf_path, page_index, ocr_cache, pdf_doc):

    page_number = page_index + 1

    cache_key = (pdf_path, page_number)

    if cache_key in ocr_cache:

        return ocr_cache[cache_key]

    with open(pdf_path, "rb") as f:

        pdf_reader = PyPDF2.PdfReader(f)

        text = pdf_reader.pages[page_index].extract_text() or ""

    if text.strip() and len(text.strip()) >= 20:

        return text

    print(
        f"Page {page_number} has no text layer, "
        "running OCR..."
    )

    page = pdf_doc[page_index]

    pix = page.get_pixmap(dpi=200)

    temp_path = os.path.join(
        os.environ.get("TEMP", "."),
        f"_ocr_page_{page_number}.png"
    )

    pix.save(temp_path)

    try:

        text = pytesseract.image_to_string(
            temp_path,
            lang="eng"
        ) or ""

    finally:

        if os.path.exists(temp_path):
            os.remove(temp_path)

    ocr_cache[cache_key] = text

    if page_number % 25 == 0:
        print(f"OCR progress: page {page_number}")

    save_ocr_cache(ocr_cache)

    return text


def chunk_page_text(text, chunk_size, chunk_overlap):
    """Split text into word-aligned chunks of roughly chunk_size characters."""

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

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


def pdf_to_vectors(pdf_path):

    print(f"\nReading PDF: {pdf_path}")

    with open(pdf_path, "rb") as f:

        pdf_reader = PyPDF2.PdfReader(f)

        total_pages = len(pdf_reader.pages)

        print(f"Total pages: {total_pages}")

    ocr_cache = load_ocr_cache()

    print(f"Loaded OCR cache: {len(ocr_cache)} pages")

    pdf_doc = pymupdf.open(pdf_path)

    page_texts = []

    for page_num in range(total_pages):

        page_text = extract_page_text(
            pdf_path,
            page_num,
            ocr_cache,
            pdf_doc
        )

        page_texts.append({
            "text": page_text,
            "page_number": page_num + 1
        })

    pdf_doc.close()

    chunks = []
    chunk_metadata = []

    for page in page_texts:

        page_text = page["text"]
        page_number = page["page_number"]

        if not page_text.strip():
            continue

        page_chunks = chunk_page_text(
            page_text,
            config.CHUNK_SIZE,
            config.CHUNK_OVERLAP
        )

        for chunk_index, chunk_text in enumerate(page_chunks):

            chunks.append(chunk_text)

            chunk_metadata.append({
                "page_number": page_number,
                "chunk_index": chunk_index
            })

    print(f"Created {len(chunks)} chunks")

    if not chunks:

        print("No text found in PDF.")

        return None, [], []

    print("\nCreating local embeddings...")

    embeddings = get_embedding_model().encode(
        chunks,
        show_progress_bar=True,
        convert_to_numpy=True
    )

    embeddings = np.array(
        embeddings,
        dtype="float32"
    )

    print(
        f"Vector shape: {embeddings.shape}"
    )

    faiss.normalize_L2(embeddings)

    print("Creating FAISS index...")

    dimension = embeddings.shape[1]

    index = faiss.IndexFlatIP(
        dimension
    )

    index.add(embeddings)

    print("Saving FAISS index...")

    faiss.write_index(
        index,
        config.INDEX_PATH
    )

    print("Saving chunks and metadata...")

    with open(config.CHUNKS_PATH, "wb") as f:

        pickle.dump(
            {
                "chunks": chunks,
                "metadata": chunk_metadata,
                "total_pages": total_pages
            },
            f
        )

    print("\nVECTOR DATABASE CREATED")

    print("Files created:")

    print(f"   {config.INDEX_PATH}")
    print(f"   {config.CHUNKS_PATH}")

    print(
        f"\nNumber of chunks: {len(chunks)}"
    )

    print(
        f"Vector dimension: "
        f"{embeddings.shape[1]}"
    )

    return (
        embeddings,
        chunks,
        chunk_metadata
    )


def find_latest_pdf():

    if not os.path.isdir(config.DOCUMENTS_DIR):
        return None

    pdfs = [
        os.path.join(config.DOCUMENTS_DIR, f)
        for f in os.listdir(config.DOCUMENTS_DIR)
        if f.lower().endswith(".pdf")
    ]

    if not pdfs:
        return None

    return max(pdfs, key=os.path.getmtime)


def main():

    pdf_file = (
        sys.argv[1]
        if len(sys.argv) > 1
        else find_latest_pdf()
    )

    if not pdf_file:

        print(
            f"No PDF found. Run with a path or add a PDF to "
            f"{config.DOCUMENTS_DIR}/."
        )

        sys.exit(1)

    pdf_to_vectors(pdf_file)

    print("\nSetup completed!")


if __name__ == "__main__":
    main()
