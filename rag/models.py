from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    title: str
    source: str
    text: str


@dataclass(frozen=True)
class Chunk:
    id: str
    title: str
    source: str
    text: str
