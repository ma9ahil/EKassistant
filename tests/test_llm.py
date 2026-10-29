import os
import unittest

import requests
from unittest.mock import Mock, patch

from rag.llm import generate_answer, generate_answer_with_metadata


class VercelGenerationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'RAG_LLM_PROVIDER': 'vercel',
            'AI_GATEWAY_API_KEY': 'test-key',
            'VERCEL_AI_MAX_TOKENS': '2048',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.passages = [{'title': 'Handbook', 'source': 'https://example.com',
                          'text': 'The team shares written updates before every planning meeting.',
                          'score': 0.9}]

    @patch('rag.llm.post_vercel_chat')
    def test_both_entry_points_return_gateway_answer_and_honor_budget(self, post):
        post.return_value = Mock(json=lambda: {'choices': [
            {'message': {'content': 'Share written updates before planning. [1]'}}]})
        result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertFalse(result.used_fallback)
        self.assertEqual(result.answer, 'Share written updates before planning. [1]')
        self.assertEqual(generate_answer('How do we plan?', self.passages), result.answer)
        for call in post.call_args_list:
            self.assertEqual(call.args[0]['max_tokens'], 2048)
            self.assertIn(self.passages[0]['text'], call.args[0]['messages'][1]['content'])

    @patch('rag.llm.post_vercel_chat')
    def test_reasoning_budget_exhaustion_explains_fallback(self, post):
        post.return_value = Mock(json=lambda: {'choices': [
            {'message': {'content': ''}, 'finish_reason': 'length'}],
            'usage': {'completion_tokens': 2048}})
        result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertTrue(result.used_fallback)
        self.assertIn('finish_reason=length', result.error)
        self.assertIn('VERCEL_AI_MAX_TOKENS', result.error)

    @patch('rag.llm.post_vercel_chat')
    def test_retired_model_reports_http_error(self, post):
        response = requests.Response()
        response.status_code = 404
        response._content = b'{"error":{"message":"Model free tier ended"}}'
        post.return_value = response
        result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertTrue(result.used_fallback)
        self.assertIn('HTTP 404', result.error)
        self.assertIn('free tier ended', result.error)

    @patch('rag.llm.post_vercel_chat')
    def test_low_relevance_does_not_call_gateway(self, post):
        result = generate_answer_with_metadata('Unrelated question', [{**self.passages[0], 'score': 0.01}])
        self.assertTrue(result.used_fallback)
        post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
