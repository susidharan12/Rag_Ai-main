"""Settings for the multi-document RAG stack.

Kept separate from config.py on purpose: the legacy Week 3/4 CLI pipeline
(pdf_reader.py / query.py) keeps its own settings and files untouched.
"""

import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, ".env"))

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

CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "1200"))
# Larger context windows keep full answer sentences together while still
# preserving continuity across section boundaries.
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "300"))

TOP_K = int(os.environ.get("RAG_TOP_K", "5"))
MIN_SCORE = float(os.environ.get("RAG_MIN_SCORE", "0.08"))

# Version-preference re-rank (Week 5 M1/M2 fix): a small lift for the resolved
# SDK version so a near-identical v2 page stops outranking the current v3 one.
VERSION_PREFERENCE_BONUS = float(
    os.environ.get("RAG_VERSION_BONUS", "0.10"))
VERSION_PREJUDICE_PENALTY = float(
    os.environ.get("RAG_VERSION_PENALTY", "0.05"))

GROQ_URL = os.environ.get(
    "GROQ_URL", "https://api.groq.com/openai/v1/chat/completions"
)
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_TIMEOUT = int(os.environ.get("GROQ_TIMEOUT", "60"))

DEFAULT_GENERATOR = os.environ.get("RAG_GENERATOR", "groq")
PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "v1")

# Relevance gate for the deterministic extractor (Week 5 M3): the best
# retrieval score must clear the embedding noise floor before we answer.
MIN_ANSWER_SCORE = float(os.environ.get("RAG_MIN_ANSWER_SCORE", "0.30"))
EXTRACTIVE_MAX_SENTENCES = int(
    os.environ.get("RAG_EXTRACTIVE_MAX_SENTENCES", "4"))

# Generators that get a wider over-fetched retrieval window so structured
# extraction can reach the parameter/error row even when it is outranked.
GENERATORS_OVERFETCH = {"extractive"}
EXTRACTIVE_CONTEXT = int(os.environ.get("RAG_EXTRACTIVE_CONTEXT", "12"))


def ensure_dirs():
    os.makedirs(INDEX_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(TRACES_PATH), exist_ok=True)
