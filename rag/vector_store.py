from __future__ import annotations

import chromadb
from chromadb.utils import embedding_functions

from rag.config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL
from rag.models import Chunk


def get_collection(reset: bool = False):
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedder,
        metadata={"hnsw:space": "cosine"},
    )


def index_chunks(chunks: list[Chunk], reset: bool = False) -> int:
    collection = get_collection(reset=reset)
    if not chunks:
        return collection.count()

    collection.upsert(
        ids=[chunk.id for chunk in chunks],
        documents=[chunk.text for chunk in chunks],
        metadatas=[
            {"title": chunk.title, "source": chunk.source}
            for chunk in chunks
        ],
    )
    return collection.count()


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    result = collection.query(query_texts=[query], n_results=top_k)
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    rows: list[dict] = []
    for doc, meta, distance in zip(docs, metas, distances):
        rows.append(
            {
                "text": doc,
                "title": meta.get("title", "Untitled"),
                "source": meta.get("source", ""),
                "score": max(0.0, 1.0 - float(distance)),
            }
        )
    return rows
