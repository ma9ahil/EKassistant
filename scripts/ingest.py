from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from rag.chunking import chunk_documents
from rag.config import PROCESSED_DIR, RAW_DIR, SEED_URLS_PATH
from rag.loaders import discover_handbook_urls, load_local_documents, load_url, read_seed_urls
from rag.vector_store import index_chunks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest GitLab handbook pages into ChromaDB.")
    parser.add_argument("--limit", type=int, default=40, help="Maximum number of URLs to ingest.")
    parser.add_argument("--discover", action="store_true", help="Discover handbook links from the main handbook page.")
    parser.add_argument("--local-dir", type=Path, default=RAW_DIR, help="Optional directory of PDFs/txt/md files.")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    urls = read_seed_urls(SEED_URLS_PATH)
    if args.discover:
        urls = list(dict.fromkeys(urls + discover_handbook_urls("https://handbook.gitlab.com/handbook/", args.limit)))
    urls = urls[: args.limit]

    documents = []
    for url in urls:
        try:
            doc = load_url(url)
            if len(doc.text) > 500:
                documents.append(doc)
                print(f"Loaded {url}")
        except Exception as exc:
            print(f"Skipped {url}: {exc}")

    if args.local_dir.exists():
        documents.extend(load_local_documents(args.local_dir.rglob("*")))

    chunks = chunk_documents(documents)
    count = index_chunks(chunks, reset=True)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "documents": [{"title": doc.title, "source": doc.source, "characters": len(doc.text)} for doc in documents],
        "chunks": len(chunks),
        "collection_count": count,
    }
    (PROCESSED_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Indexed {len(chunks)} chunks from {len(documents)} documents. Collection count: {count}")


if __name__ == "__main__":
    main()
