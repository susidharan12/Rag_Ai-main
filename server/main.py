"""Nimbus Docs Assistant — API server.

Run:  python -m uvicorn server.main:app --reload --port 8000

Serves the React build from frontend/dist at "/" when present.
"""

import os   
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rag_core import settings
from rag_core.pipeline import ask_sync, get_store
from rag_core.store import DocStore

app = FastAPI(title="RAG Docs Assistant", version="5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_store = DocStore()


@app.on_event("startup")
def _startup():
    settings.ensure_dirs()
    _store.ensure_loaded()


# ------------------------------------------------------------------ docs ----


@app.post("/api/documents")
async def upload_documents(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "No files received")

    reports = []
    for f in files:
        data = await f.read()
        if not data:
            reports.append({"status": "error", "name": f.filename,
                            "detail": "empty file"})
            continue
        if not f.filename.lower().endswith((".pdf", ".md", ".markdown", ".txt")):
            reports.append({"status": "unsupported", "name": f.filename})
            continue
        try:
            report = _store.add_document(f.filename, data)
        except Exception as e:  # surface per-file failures, keep the rest
            reports.append({"status": "error", "name": f.filename,
                            "detail": str(e)})
            continue
        reports.append(report)

    return {"reports": reports, "stats": _store.stats()}


@app.get("/api/documents")
def list_documents():
    return {"documents": _store.list_documents(), "stats": _store.stats()}


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    removed = _store.delete_document(doc_id)
    if not removed:
        raise HTTPException(404, f"Unknown doc_id {doc_id}")
    return {"removed": removed["name"], "stats": _store.stats()}


# ------------------------------------------------------------------- ask ----


class AskRequest(BaseModel):
    question: str
    generator: str | None = None
    top_k: int | None = None


@app.post("/api/ask")
def ask(req: AskRequest):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(400, "Empty question")
    payload, trace = ask_sync(
        question,
        generator=req.generator,
        top_k=req.top_k,
        surface="ui" if req.generator else "api",
        store=_store,
    )
    payload["trace"] = trace
    return payload


@app.get("/api/health")
def health():
    stats = _store.stats()
    return {"ok": True, "index": stats}


# ---------------------------------------------------------------- static ----

_DIST = os.path.join(settings.BASE_DIR, "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")),
              name="assets")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(_DIST, "index.html"))

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = os.path.join(_DIST, path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_DIST, "index.html"))
