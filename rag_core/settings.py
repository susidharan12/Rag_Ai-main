"""Settings for the multi-document RAG stack.

Kept separate from config.py on purpose: the legacy Week 3/4 CLI pipeline
(pdf_reader.py / query.py) keeps its own settings and files untouched.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.environ.get("RAG_DATA_DIR", os.path.join(BASE_DIR, "data"))
INDEX_DIR = os.path.join(DATA_DIR, "index")
REGISTRY_PATH = os.path.join(INDEX_DIR, "registry.json")
CHUNKS_PATH = os.path.join(INDEX_DIR, "chunks.pkl")

UPLOADS_DIR = os.environ.get("RAG_UPLOADS_DIR", os.path.join(DATA_DIR, "uploads"))
TRACES_PATH = os.environ.get(
    "RAG_TRACES_PATH",
    os.path.join(BASE_DIR, "week5_error_analysis", "traces", "traces.jsonl"),
)

EMBEDDING_MODEL_NAME = os.environ.get(
    "RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "250"))

TOP_K = int(os.environ.get("RAG_TOP_K", "3"))
MIN_SCORE = float(os.environ.get("RAG_MIN_SCORE", "0.12"))

OLLAMA_URL = os.environ.get("RAG_OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("RAG_OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.environ.get("RAG_OLLAMA_TIMEOUT", "120"))

DEFAULT_GENERATOR = os.environ.get("RAG_GENERATOR", "ollama")
PROMPT_VERSION_LLM = "grounded-strict-v2"
PROMPT_VERSION_EXTRACTIVE = "extractive-grounded-v1"


def ensure_dirs():
    os.makedirs(INDEX_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(TRACES_PATH), exist_ok=True)
