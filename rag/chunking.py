from __future__ import annotations

import hashlib
from typing import Iterable

from rag.models import Chunk, Document


def chunk_text(text: str, chunk_size: int = 1100, overlap: int = 180) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= chunk_size:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
            current = current[-overlap:] if overlap else ""
        if len(paragraph) > chunk_size:
            for start in range(0, len(paragraph), chunk_size - overlap):
                chunks.append(paragraph[start : start + chunk_size])
            current = ""
        else:
            current = f"{current}\n\n{paragraph}".strip()

    if current:
        chunks.append(current)
    return chunks


def chunk_documents(documents: Iterable[Document]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in documents:
        for index, text in enumerate(chunk_text(doc.text)):
            digest = hashlib.sha1(f"{doc.source}:{index}:{text[:80]}".encode("utf-8")).hexdigest()[:16]
            chunks.append(Chunk(id=digest, title=doc.title, source=doc.source, text=text))
    return chunks
