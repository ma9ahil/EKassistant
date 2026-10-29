"""Export only seed-listed public handbook pages from the local index."""
from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.bootstrap import SNAPSHOT_PATH
from rag.config import EMBEDDING_MODEL, SEED_URLS_PATH
from rag.loaders import read_seed_urls
from rag.vector_store import get_collection


def main():
    allowed = set(read_seed_urls(SEED_URLS_PATH))
    data = get_collection().get(include=['documents', 'metadatas', 'embeddings'])
    rows = []
    for index, metadata in enumerate(data['metadatas']):
        if metadata.get('source') not in allowed:
            continue
        rows.append({
            'id': data['ids'][index], 'text': data['documents'][index],
            'title': metadata['title'], 'source': metadata['source'],
            'embedding': [round(float(value), 7) for value in data['embeddings'][index]],
        })
    if not rows:
        raise RuntimeError('Load the public handbook before exporting a demo snapshot.')
    snapshot = {'embedding_model': EMBEDDING_MODEL,
                'exported_at': datetime.now(timezone.utc).isoformat(), 'chunks': rows}
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(SNAPSHOT_PATH, 'wt', encoding='utf-8') as handle:
        json.dump(snapshot, handle, separators=(',', ':'))
    print(f'Exported {len(rows)} public handbook sections to {SNAPSHOT_PATH.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
