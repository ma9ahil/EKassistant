from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from rag.models import Document


HEADERS = {
    "User-Agent": "EKassistant/0.1 (+portfolio RAG demo)"
}


class HandbookLoadError(RuntimeError):
    """Raised when a handbook page cannot be loaded as public documentation."""


def read_seed_urls(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def normalize_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def discover_handbook_urls(seed_url: str, limit: int = 50) -> list[str]:
    response = requests.get(seed_url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        href = urljoin(seed_url, anchor["href"].split("#")[0])
        parsed = urlparse(href)
        if parsed.netloc != "handbook.gitlab.com":
            continue
        if not parsed.path.startswith("/handbook/"):
            continue
        if href in seen:
            continue
        seen.add(href)
        urls.append(href)
        if len(urls) >= limit:
            break

    return urls


def load_url(url: str) -> Document:
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HandbookLoadError(f"Could not load {url}: {exc}") from exc

    final_url = response.url.split("#")[0]
    parsed = urlparse(final_url)
    if parsed.netloc != "handbook.gitlab.com" or not parsed.path.startswith("/handbook/"):
        raise HandbookLoadError(f"Skipped non-handbook redirect: {url} -> {final_url}")

    soup = BeautifulSoup(response.text, "html.parser")

    for element in soup(["script", "style", "nav", "footer", "aside", "form"]):
        element.decompose()

    title = soup.find("h1")
    page_title = normalize_text(title.get_text(" ")) if title else (soup.title.string if soup.title else url)
    main = soup.find("main") or soup.body or soup
    text = normalize_text(main.get_text("\n"))
    return Document(title=page_title, source=final_url, text=text)


def load_pdf(path: Path) -> Document:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PDF loading requires pypdf. Install dependencies with `pip install -r requirements.txt`."
        ) from exc

    reader = PdfReader(str(path))
    text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return Document(title=path.stem, source=str(path), text=normalize_text(text))


def load_local_documents(paths: Iterable[Path]) -> list[Document]:
    docs: list[Document] = []
    for path in paths:
        if path.suffix.lower() == ".pdf":
            docs.append(load_pdf(path))
        elif path.suffix.lower() in {".txt", ".md"}:
            docs.append(Document(title=path.stem, source=str(path), text=normalize_text(path.read_text(encoding="utf-8"))))
    return docs
