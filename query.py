import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pickle

import faiss
import numpy as np
import requests
from sentence_transformers import SentenceTransformer

import config

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

    context = ""

    for result in results:

        page_number = result["metadata"]["page_number"]

        context += (
            f"\n--- Document Chunk "
            f"{result['rank']} "
            f"(Page {page_number}) ---\n"
        )

        context += result["chunk"]
        context += "\n"
   
    prompt = f"""
You are a helpful question-answering assistant.

Answer the user's question using ONLY the
information provided in the document context.

If the answer cannot be found in the context,
say:

"I could not find the answer in the provided document."

Do not make up information. Keep the answer short:
4 to 5 lines maximum, no headers or bullet lists.

Document context:
{context}

User question:
{query}

Answer:
"""

    print(prompt)
    try:

        response = requests.post(
            config.OLLAMA_URL,
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=300
        )

        response.raise_for_status()

        data = response.json()

        return data["response"]

    except requests.exceptions.ConnectionError:

        return (
            "Could not connect to Ollama.\n\n"
            "Make sure Ollama is installed and running."
        )

    except requests.exceptions.RequestException as e:

        return f"Ollama request failed: {e}"


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
