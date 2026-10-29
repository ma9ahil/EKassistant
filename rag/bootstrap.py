"""Restore a portable, public-only search snapshot without scraping or paid APIs."""
from __future__ import annotations

import gzip
import json
import threading
from pathlib import Path

from rag.config import EMBEDDING_MODEL, ROOT_DIR

SNAPSHOT_PATH = ROOT_DIR / 'data' / 'demo' / 'handbook.json.gz'
_bootstrap_lock = threading.Lock()


def ensure_knowledge_base(collection=None, snapshot_path: Path = SNAPSHOT_PATH) -> int:
    if collection is None:
        from rag.vector_store import get_collection
        collection = get_collection()
    with _bootstrap_lock:
        if collection.count():
            return collection.count()
        with gzip.open(snapshot_path, 'rt', encoding='utf-8') as handle:
            snapshot = json.load(handle)
        if snapshot['embedding_model'] != EMBEDDING_MODEL:
            raise ValueError('The bundled handbook snapshot uses a different embedding model.')
        rows = snapshot['chunks']
        if not rows:
            raise ValueError('The bundled handbook snapshot is empty.')
        # One transaction avoids exposing a half-restored demo index.
        collection.upsert(
            ids=[row['id'] for row in rows],
            documents=[row['text'] for row in rows],
            metadatas=[{'title': row['title'], 'source': row['source']} for row in rows],
            embeddings=[row['embedding'] for row in rows],
        )
        return collection.count()
