"""Multi-document RAG core shared by the API server and analysis scripts."""

from rag_core.pipeline import ask, ask_sync
from rag_core.store import DocStore

__all__ = ["ask", "ask_sync", "DocStore"]
