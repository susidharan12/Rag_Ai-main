"""Multi-document vector store.

State lives in two files under data/index/:
  registry.json  — one entry per uploaded document
  chunks.pkl     — {"documents": {...}, "chunks": [...], "metadata": [...],
                    "embeddings": np.ndarray(float32, L2-normalized)}

The FAISS IndexFlatIP is derived from the stored embeddings and rebuilt
whenever documents are added or removed. Corpora at this scale make full
rebuilds effectively free and keep the file format simple and debuggable.
"""

import datetime
import hashlib
import os
import pickle
import re
import threading
import uuid

import faiss
import numpy as np

from rag_core import settings
from rag_core.chunker import chunk_pages
from rag_core.extract import extract_pages

_embedding_model = None
_lock = threading.Lock()


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _embedding_model


def _slug(name):
    """Path-aware slug so v2/client_connect.md and v3/client_connect.md
    never produce colliding chunk_id prefixes."""

    parts = re.split(r"[\\/]+", name)
    stem_parts = []
    for part in parts[:-1]:
        if part.lower() in ("", "corpus", "documents"):
            continue
        stem_parts.append(part)
    stem_parts.append(os.path.splitext(parts[-1])[0])
    return re.sub(r"[^a-z0-9]+", "-", "-".join(stem_parts).lower()).strip("-") \
        or "doc"


def _embed(texts):
    vectors = get_embedding_model().encode(
        texts, show_progress_bar=False, convert_to_numpy=True
    )
    vectors = np.array(vectors, dtype="float32")
    faiss.normalize_L2(vectors)
    return vectors


class DocStore:
    def __init__(self):
        settings.ensure_dirs()
        self._state = None

    # ---------- persistence ----------

    def _load(self):
        if self._state is not None:
            return self._state

        if os.path.exists(settings.CHUNKS_PATH):
            with open(settings.CHUNKS_PATH, "rb") as f:
                state = pickle.load(f)
        else:
            state = {"documents": {}, "chunks": [], "metadata": [],
                     "embeddings": np.zeros((0, 384), dtype="float32")}

        if os.path.exists(settings.REGISTRY_PATH):
            with open(settings.REGISTRY_PATH, "r", encoding="utf-8") as f:
                state["documents"] = {
                    d["doc_id"]: d for d in __import__("json").load(f)
                }

        self._state = state
        return state

    def _save(self):
        # Atomic persistence (Week 5 S1): write to a temp file then rename so a
        # crash mid-write can never leave a truncated/corrupt chunks.pkl next to
        # an updated registry.json. Both files are swapped in the same pass.
        state = self._state
        import json

        chunks_tmp = settings.CHUNKS_PATH + ".tmp"
        with open(chunks_tmp, "wb") as f:
            pickle.dump(state, f)
        os.replace(chunks_tmp, settings.CHUNKS_PATH)

        reg_tmp = settings.REGISTRY_PATH + ".tmp"
        with open(reg_tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(state["documents"].values(),
                             key=lambda d: d["added_at"]), f, indent=2)
        os.replace(reg_tmp, settings.REGISTRY_PATH)

    def _rebuild_index(self):
        emb = self._state["embeddings"]
        if emb.shape[0] == 0:
            self._index = None
            return
        index = faiss.IndexFlatIP(emb.shape[1])
        index.add(emb)
        self._index = index

    def ensure_loaded(self):
        with _lock:
            if self._state is not None:
                return
            self._load()
            self._index = None
            self._rebuild_index()

    # ---------- documents ----------

    def add_document(self, file_name, data, surface="api"):
        """Ingest one uploaded file. Returns a per-file report dict."""

        with _lock:
            self._load()
            meta_front, pages = extract_pages(file_name, data)
            doc_id = f"{_slug(file_name)}-{uuid.uuid4().hex[:6]}"
            content_hash = hashlib.sha256(data).hexdigest()[:12]

            for existing in self._state["documents"].values():
                if existing.get("content_hash") == content_hash:
                    return {"status": "duplicate", "doc_id": existing["doc_id"],
                            "name": existing["name"]}

            page_meta = []
            for p in pages:
                p["sdk_version"] = meta_front.get("sdk_version", "")
                p["doc_title"] = meta_front.get("title",
                                                os.path.splitext(
                                                    os.path.basename(file_name))[0])
                page_meta.append(p)

            pairs = chunk_pages(page_meta,
                                settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
            if not pairs:
                return {"status": "empty", "doc_id": doc_id, "name": file_name}

            texts = [t for t, _ in pairs]
            vectors = _embed(texts)

            start = len(self._state["chunks"])
            for i, (text, meta) in enumerate(pairs):
                meta.update({
                    "doc_id": doc_id,
                    "chunk_id": f"{_slug(file_name)}-{doc_id.rsplit('-', 1)[-1]}:p{meta['page_number']}:c{meta['chunk_index']}",
                    "source_file": os.path.basename(file_name),
                })
                self._state["chunks"].append(text)
                self._state["metadata"].append(meta)

            self._state["embeddings"] = np.vstack(
                [self._state["embeddings"], vectors])

            self._state["documents"][doc_id] = {
                "doc_id": doc_id,
                "name": os.path.basename(file_name),
                "source_file": os.path.basename(file_name),
                "content_hash": content_hash,
                "sdk_version": meta_front.get("sdk_version", ""),
                "pages": len(pages),
                "chunks": len(pairs),
                "chars": sum(len(t) for t in texts),
                "added_at": datetime.datetime.utcnow().isoformat() + "Z",
                "vector_offset": start,
            }
            self._save()
            self._rebuild_index()
            return {"status": "indexed", **self._state["documents"][doc_id]}

    def delete_document(self, doc_id):
        with _lock:
            self._load()
            info = self._state["documents"].get(doc_id)
            if not info:
                return None

            keep_idx = [i for i, m in enumerate(self._state["metadata"])
                        if m["doc_id"] != doc_id]
            self._state["chunks"] = [self._state["chunks"][i] for i in keep_idx]
            self._state["metadata"] = [self._state["metadata"][i] for i in keep_idx]
            self._state["embeddings"] = self._state["embeddings"][keep_idx] \
                if keep_idx else np.zeros((0, self._state["embeddings"].shape[1]
                                           or 384), dtype="float32")
            del self._state["documents"][doc_id]
            self._recompute_offsets()
            self._save()
            self._rebuild_index()
            return info

    def _recompute_offsets(self):
        """Refresh every document's vector_offset after a delete so consumers
        never read into another document's vectors (Week 5 S3)."""
        seen = {}
        for i, m in enumerate(self._state["metadata"]):
            if m["doc_id"] not in seen:
                seen[m["doc_id"]] = i
        for d in self._state["documents"].values():
            d["vector_offset"] = seen.get(d["doc_id"], 0)

    def list_documents(self):
        self.ensure_loaded()
        docs = sorted(self._state["documents"].values(), key=lambda d: d["added_at"])
        return [{
            **d,
            "total_chunks": len(self._state["chunks"]),
        } for d in docs]

    def stats(self):
        self.ensure_loaded()
        versions = {}
        for m in self._state["metadata"]:
            v = m.get("sdk_version") or "unversioned"
            versions[v] = versions.get(v, 0) + 1
        return {"documents": len(self._state["documents"]),
                "chunks": len(self._state["chunks"]),
                "by_sdk_version": versions}

    # ---------- retrieval ----------

    def search(self, query, top_k=None, min_score=None):
        self.ensure_loaded()
        top_k = top_k or settings.TOP_K
        min_score = settings.MIN_SCORE if min_score is None else min_score

        if self._index is None or not self._state["chunks"]:
            return []

        # Over-fetch a bit more than top_k so version re-ranking has room to
        # promote a current-value chunk that raw similarity put just below the
        # cut (the stale-v2 fix from Week 5's pre-registered prediction).
        fetch = max(top_k * 2 + 4, top_k)

        vec = np.array(
            get_embedding_model().encode([query], convert_to_numpy=True),
            dtype="float32",
        )
        faiss.normalize_L2(vec)

        scores, ids = self._index.search(vec, min(fetch, len(self._state["chunks"])))

        pref = _resolve_version_preference(query)
        rows = []
        for idx, score in zip(ids[0], scores[0]):
            if idx == -1 or score < min_score:
                continue
            meta = self._state["metadata"][idx]
            version = meta.get("sdk_version", "")
            score_used = float(score)
            # Version preference is a re-rank bonus, not a hard filter: the
            # preferred version gets a small lift so a near-identical v2 page no
            # longer outranks the current v3 page, while unversioned chunks
            # (sports PDF, reserved for sdk_version="") and genuinely different
            # topics keep their raw similarity ordering.
            if pref and version:
                if pref == "both":
                    pass
                elif version == pref:
                    score_used += settings.VERSION_PREFERENCE_BONUS
                elif pref != "both" and version not in (pref, ""):
                    score_used -= settings.VERSION_PREJUDICE_PENALTY
            rows.append((score_used, idx, float(score), meta))

        # Stable re-rank by preference-adjusted similarity.
        rows.sort(key=lambda r: -r[0])

        results = []
        for rank, (_, idx, raw_score, meta) in enumerate(rows[:top_k], start=1):
            results.append({
                "rank": rank,
                "chunk_id": meta["chunk_id"],
                "score": round(raw_score, 4),
                "source_doc": meta["source_file"],
                "doc_id": meta["doc_id"],
                "page_number": meta["page_number"],
                "section": meta.get("section", ""),
                "sdk_version": meta.get("sdk_version", ""),
                "text": self._state["chunks"][idx],
            })
        return results


def _resolve_version_preference(query):
    """Return the SDK version the query most likely wants.

    v3 (current) is the default for a versionless question. A query that names
    v2 (and not v3) prefers v2. A query that names both, or that asks about a
    change/comparison/difference, needs both and returns 'both'. Unversioned
    queries with no SDK intent return None (no re-ranking at all).
    """
    q = query.lower()
    mentions_v2 = bool(re.search(r"\bv2\b|\bsdk\s*v2\b", q))
    mentions_v3 = bool(re.search(r"\bv3\b|\bsdk\s*v3\b", q))
    wants_both = bool(re.search(
        r"compare|difference\s+between|changed|differ|\bsdk v2 and v3\b|"
        r"v2\s+and\s+v3\b|v3\s+and\s+v2\b|vs\.?\s*(v2|v3)|(?:v2|v3)\s*vs",
        q))
    if wants_both or (mentions_v2 and mentions_v3):
        return "both"
    if mentions_v2:
        return "v2"
    if mentions_v3:
        return "v3"
    return "v3"
