import os
import shutil

EMBEDDING_MODEL_NAME = os.environ.get(
    "RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "250"))
TOP_K = int(os.environ.get("RAG_TOP_K", "3"))
MIN_SCORE = float(os.environ.get("RAG_MIN_SCORE", "0.12"))

DOCUMENTS_DIR = os.environ.get("RAG_DOCUMENTS_DIR", "documents")
INDEX_PATH = os.environ.get("RAG_INDEX_PATH", "vectors.index")
CHUNKS_PATH = os.environ.get("RAG_CHUNKS_PATH", "chunks.pkl")
OCR_CACHE_PATH = os.environ.get("RAG_OCR_CACHE_PATH", "ocr_cache.pkl")


def resolve_tesseract_cmd():
    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd:
        return env_cmd

    found = shutil.which("tesseract")
    if found:
        return found

    return r"C:\Program Files\Tesseract-OCR\tesseract.exe"
