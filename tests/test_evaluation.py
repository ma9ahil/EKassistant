import unittest
from unittest.mock import Mock, patch

from rag.ranking import select_passages
from scripts.evaluate import first_relevant_rank, reference_source, summarize


class RetrievalMetricsTests(unittest.TestCase):
    def test_hit_and_reciprocal_rank_include_misses(self):
        metrics = summarize([{'first_relevant_rank': rank} for rank in [1, 2, None]], 5)
        self.assertEqual(metrics['hits'], 2)
        self.assertAlmostEqual(metrics['hit_at_k'], 2 / 3)
        self.assertEqual(metrics['mrr_at_k'], 0.5)

    def test_exact_page_matching(self):
        passages = [{'source': 'https://example.com/engineering/quality/'},
                    {'source': 'https://example.com/engineering/'}]
        self.assertEqual(first_relevant_rank(passages, 'https://example.com/engineering'), 2)
        self.assertIsNone(first_relevant_rank(passages, 'https://example.com/security/'))

    def test_legacy_hint_resolves_full_seed_url(self):
        source = reference_source({'expected_source_hint': '/asynchronous/'})
        self.assertEqual(source, 'https://handbook.gitlab.com/handbook/company/culture/all-remote/asynchronous/')

    def test_empty_metrics(self):
        self.assertEqual(summarize([], 5)['mrr_at_k'], 0)


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'source': url, 'text': str(i), 'score': 0.9 - i / 10}
                     for i, url in enumerate(['https://a/', 'https://a', 'https://b/', 'https://c/'])]

    def test_similarity_preserves_order_and_duplicates(self):
        self.assertEqual(select_passages(self.rows, 3), self.rows[:3])

    def test_diversity_keeps_best_chunk_per_page_in_order(self):
        self.assertEqual(select_passages(self.rows, 3, 'source_diversity'),
                         [self.rows[0], self.rows[2], self.rows[3]])
        self.assertEqual(len(self.rows), 4)

    def test_invalid_strategy(self):
        with self.assertRaises(ValueError):
            select_passages(self.rows, 3, 'unknown')

    def test_app_retrieval_uses_shared_ranking_and_caps_candidates(self):
        from rag.vector_store import retrieve
        collection = Mock()
        collection.count.return_value = 4
        collection.query.return_value = {
            'documents': [[row['text'] for row in self.rows]],
            'metadatas': [[{'title': 'Test', 'source': row['source']} for row in self.rows]],
            'distances': [[1 - row['score'] for row in self.rows]],
        }
        with patch('rag.vector_store.get_collection', return_value=collection):
            result = retrieve('test', top_k=3, strategy='source_diversity')
        self.assertEqual([row['source'] for row in result], ['https://a/', 'https://b/', 'https://c/'])
        self.assertEqual(collection.query.call_args.kwargs['n_results'], 4)
