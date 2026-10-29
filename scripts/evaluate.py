"""Evaluate reference-page retrieval against the bundled demo snapshot, without LLM calls."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rag.bootstrap import SNAPSHOT_PATH, ensure_knowledge_base
from rag.config import EMBEDDING_MODEL, SEED_URLS_PATH
from rag.loaders import read_seed_urls
from rag.ranking import select_passages


def reference_source(row: dict) -> str:
    if row.get('expected_source'):
        return row['expected_source']
    hint = row['expected_source_hint']
    matches = [url for url in read_seed_urls(SEED_URLS_PATH) if url.endswith(hint)]
    if len(matches) != 1:
        raise ValueError(f'Reference hint must identify one seed page: {hint}')
    return matches[0]


def first_relevant_rank(passages: list[dict], expected_source: str) -> int | None:
    # Exact source-page matching avoids credit for parent/sibling URLs.
    expected = expected_source.rstrip('/')
    return next((rank for rank, passage in enumerate(passages, 1)
                 if passage['source'].rstrip('/') == expected), None)


def summarize(rows: list[dict], k: int) -> dict:
    ranks = [row['first_relevant_rank'] for row in rows]
    hits = sum(rank is not None for rank in ranks)
    return {
        'questions': len(rows), 'k': k, 'hits': hits,
        'hit_at_k': hits / len(rows) if rows else 0,
        'mrr_at_k': sum(1 / rank for rank in ranks if rank is not None) / len(rows) if rows else 0,
        'hit_at_4': sum(rank is not None and rank <= 4 for rank in ranks) / len(rows) if rows else 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--questions', type=Path, default=ROOT_DIR / 'data/eval/questions.csv')
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT_PATH)
    parser.add_argument('--k', type=int, default=5)
    parser.add_argument('--strategy', choices=['similarity', 'source_diversity', 'compare'], default='compare')
    parser.add_argument('--output', type=Path, help='Write reproducible metrics and per-question rankings to JSON.')
    args = parser.parse_args()
    if args.k < 1:
        parser.error('--k must be positive')
    return args


def main() -> None:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    args = parse_args()
    with args.questions.open(newline='', encoding='utf-8') as handle:
        questions = list(csv.DictReader(handle))
    if not questions:
        raise ValueError('The evaluation set is empty.')
    with gzip.open(args.snapshot, 'rt', encoding='utf-8') as handle:
        snapshot = json.load(handle)
    sources = {row['source'].rstrip('/') for row in snapshot['chunks']}
    strategies = ['similarity', 'source_diversity'] if args.strategy == 'compare' else [args.strategy]
    results = {strategy: [] for strategy in strategies}
    # Never reset or write into the live application's Chroma directory.
    with TemporaryDirectory(prefix='ekassistant-eval-') as tmp:
        client = chromadb.PersistentClient(path=tmp)
        collection = client.create_collection('evaluation', embedding_function=None, metadata={'hnsw:space': 'cosine'})
        ensure_knowledge_base(collection, args.snapshot)
        embedder = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        embeddings = embedder([row['question'] for row in questions])
        candidate_count = min(collection.count(), args.k * 5)
        retrieved = collection.query(query_embeddings=embeddings, n_results=candidate_count,
                                     include=['documents', 'metadatas', 'distances'])
        for index, row in enumerate(questions):
            candidates = [
                {'text': text, 'title': meta['title'], 'source': meta['source'],
                 'score': max(0.0, 1 - float(distance))}
                for text, meta, distance in zip(retrieved['documents'][index],
                                               retrieved['metadatas'][index], retrieved['distances'][index])
            ]
            expected = reference_source(row)
            for strategy in strategies:
                passages = select_passages(candidates, args.k, strategy)
                rank = first_relevant_rank(passages, expected)
                results[strategy].append({
                    'question': row['question'], 'expected_source': expected,
                    'reference_in_corpus': expected.rstrip('/') in sources,
                    'first_relevant_rank': rank,
                    'retrieved_sources': [p['source'] for p in passages],
                })
    report = {
        'evaluated_at_utc': datetime.now(timezone.utc).isoformat(),
        'embedding_model': EMBEDDING_MODEL, 'chunk_count': len(snapshot['chunks']),
        'source_count': len(sources), 'candidate_count': candidate_count,
        'questions_sha256': hashlib.sha256(args.questions.read_bytes()).hexdigest(),
        'snapshot_sha256': hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
        'versions': {name: version(name) for name in ['chromadb', 'sentence-transformers', 'transformers']},
        'strategies': {},
    }
    for strategy, rows in results.items():
        metrics = summarize(rows, args.k)
        covered = [row for row in rows if row['reference_in_corpus']]
        report['strategies'][strategy] = {
            'all_questions': metrics, 'covered_questions': summarize(covered, args.k), 'results': rows,
        }
        print(f"{strategy}: Hit@{args.k}={metrics['hit_at_k']:.2%} ({metrics['hits']}/{metrics['questions']}), "
              f"MRR@{args.k}={metrics['mrr_at_k']:.4f}; reference pages present: {len(covered)}/{len(rows)}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(f'Results saved to {args.output}')


if __name__ == '__main__':
    main()
