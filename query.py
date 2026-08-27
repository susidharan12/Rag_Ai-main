import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pickle
import re

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

import config

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "in", "on", "for",
    "to", "and", "or", "what", "which", "who", "whom", "how", "does", "do",
    "did", "can", "could", "should", "would", "when", "where", "why", "with",
    "by", "at", "from", "as", "be", "been", "it", "its", "this", "that",
    "these", "those", "there", "their", "them", "they", "i", "you", "we",
    "my", "your", "our", "me", "us", "not", "no", "yes",
}

_embedding_model = None
_index = None
_chunks = None
_metadata = None


def get_embedding_model():

    global _embedding_model

    if _embedding_model is None:
        _embedding_model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)

    return _embedding_model


def load_resources():
    """Load the FAISS index and chunk store, or raise a clear error."""

    global _index, _chunks, _metadata

    if _index is not None:
        return

    try:

        _index = faiss.read_index(config.INDEX_PATH)

        with open(config.CHUNKS_PATH, "rb") as f:
            data = pickle.load(f)

        _chunks = data["chunks"]
        _metadata = data["metadata"]

    except FileNotFoundError as e:

        raise RuntimeError(
            f"Could not find '{e.filename}'. "
            "Run 'python pdf_reader.py <path-to-pdf>' first to build the index."
        ) from e


def query_to_vector(query):

    vector = get_embedding_model().encode(
        [query],
        convert_to_numpy=True
    )

    vector = np.array(
        vector,
        dtype="float32"
    )

    faiss.normalize_L2(vector)

    return vector


def search_database(query, top_k=config.TOP_K, min_score=config.MIN_SCORE):

    load_resources()

    query_vector = query_to_vector(query)

    distances, indices = _index.search(
        query_vector,
        top_k
    )

    results = []

    for index_id, distance in zip(indices[0], distances[0]):

        if index_id == -1:
            continue

        score = float(distance)

        if score < min_score:
            continue

        results.append({
            "rank": len(results) + 1,
            "chunk": _chunks[index_id],
            "metadata": _metadata[index_id],
            "score": score
        })

    return results


def generate_answer(query, results):

    if not results:
        return (
            "I could not find the answer in the provided document."
        )

    query_terms = {
        t for t in re.findall(r"[a-z0-9_.]+", query.lower())
        if t not in _STOPWORDS and len(t) > 1
    }

    best = []

    for result in results:

        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+|\n+", result["chunk"])
            if s.strip()
        ]

        for i, sentence in enumerate(sentences):
            sent_terms = {
                t for t in re.findall(r"[a-z0-9_.]+", sentence.lower())
                if t not in _STOPWORDS and len(t) > 1
            }
            overlap = len(query_terms & sent_terms)
            if overlap <= 0:
                continue
            score = (overlap / max(1, len(query_terms)) ** 0.5) - 0.01 * i \
                    - 0.001 * result["rank"]
            best.append((score, result["rank"], i, sentence))

    if not best:
        return (
            "I could not find the answer in the provided document."
        )

    best.sort(key=lambda t: (-t[0], t[1], t[2]))

    picked = []
    seen_ranks = set()

    for _, rank, _, sentence in best:
        if rank in seen_ranks and picked:
            continue
        picked.append(sentence)
        seen_ranks.add(rank)
        if len(picked) == 2:
            break

    return " ".join(picked)


def main():

    try:
        load_resources()
    except RuntimeError as e:
        print(f"\n{e}")
        return

    while True:

        query = input(
            "\nEnter your question "
            "(or type 'exit'): "
        )

        if query.lower().strip() == "exit":

            print("Goodbye!")

            break

        if not query.strip():

            print(
                "Please enter a question."
            )

            continue

        results = search_database(query)

        answer = generate_answer(
            query,
            results
        )

        if "could not find" in answer.lower():
            status = "R"
        else:
            status = "G"

        print(f"\n[{status}] {answer}")


if __name__ == "__main__":
    main()
