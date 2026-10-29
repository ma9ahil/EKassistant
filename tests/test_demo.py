import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rag.bootstrap import SNAPSHOT_PATH, ensure_knowledge_base
from rag.config import EMBEDDING_MODEL, SEED_URLS_PATH
from rag.demo import DemoBudgetExceeded, admit_question, reserve_api_call
from rag.loaders import read_seed_urls


class DemoLimitsTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'DEMO_MODE': 'true', 'DEMO_SESSION_QUESTIONS': '2',
                                     'DEMO_COOLDOWN_SECONDS': '10', 'DEMO_SERVER_API_CALLS': '2'})
        env.start()
        self.addCleanup(env.stop)

    def test_session_limits_and_cooldown(self):
        state = {}
        self.assertIsNone(admit_question(state, now=0))
        self.assertIn('wait', admit_question(state, now=1))
        self.assertEqual(state['demo_questions'], 1)
        self.assertIsNone(admit_question(state, now=11))
        state['messages'] = []  # New conversation must not reset usage.
        self.assertIn('question limit', admit_question(state, now=30))
        self.assertEqual(state['demo_questions'], 2)

    def test_shared_budget(self):
        with patch('rag.demo._api_calls', 0):
            reserve_api_call()
            reserve_api_call()
            with self.assertRaises(DemoBudgetExceeded):
                reserve_api_call()

    def test_local_mode_unlimited(self):
        with patch.dict(os.environ, {'DEMO_MODE': 'false'}):
            state = {'demo_questions': 100}
            self.assertIsNone(admit_question(state))
            self.assertEqual(state['demo_questions'], 100)


class BootstrapTests(unittest.TestCase):
    def test_bundled_snapshot_public_sources_and_vectors(self):
        with gzip.open(SNAPSHOT_PATH, 'rt') as handle:
            snapshot = json.load(handle)
        self.assertEqual(snapshot['embedding_model'], EMBEDDING_MODEL)
        self.assertGreater(len(snapshot['chunks']), 100)
        allowed = set(read_seed_urls(SEED_URLS_PATH))
        for row in snapshot['chunks']:
            self.assertIn(row['source'], allowed)
            self.assertEqual(len(row['embedding']), 384)

    def test_cold_start_restores_without_fetching_or_generation(self):
        collection = Mock()
        collection.count.side_effect = [0, 970]
        with patch('requests.get', side_effect=AssertionError('no fetch')), patch('requests.post', side_effect=AssertionError('no API')):
            self.assertEqual(ensure_knowledge_base(collection), 970)
        self.assertGreater(len(collection.upsert.call_args.kwargs['ids']), 100)
        self.assertIn('embeddings', collection.upsert.call_args.kwargs)

    def test_existing_index_is_not_rebuilt(self):
        collection = Mock()
        collection.count.return_value = 10
        self.assertEqual(ensure_knowledge_base(collection, Path('missing.gz')), 10)
        collection.upsert.assert_not_called()

    def test_model_mismatch_does_not_write(self):
        collection = Mock()
        collection.count.return_value = 0
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'snapshot.gz'
            with gzip.open(path, 'wt') as handle:
                json.dump({'embedding_model': 'wrong', 'chunks': []}, handle)
            with self.assertRaises(ValueError):
                ensure_knowledge_base(collection, path)
        collection.upsert.assert_not_called()
