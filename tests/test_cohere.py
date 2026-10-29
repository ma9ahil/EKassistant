import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cohere.core.api_error import ApiError
from httpx import ConnectError

from rag.llm import UNSUPPORTED, add_closest_matches, generate_answer, generate_answer_with_metadata


class CohereGenerationTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            'RAG_LLM_PROVIDER': 'cohere', 'COHERE_API_KEY': 'test-key',
            'COHERE_MODEL': 'command-a-plus-05-2026', 'COHERE_MAX_TOKENS': '2048',
        })
        env.start()
        self.addCleanup(env.stop)
        self.passages = [{'title': 'Planning', 'source': 'https://example.com',
                          'text': 'The team shares written updates before every planning meeting.',
                          'score': 0.9}]
        client_patch = patch('cohere.ClientV2')
        self.factory = client_patch.start()
        self.addCleanup(client_patch.stop)
        self.chat = self.factory.return_value.__enter__.return_value.chat
        self.chat.return_value = SimpleNamespace(
            message=SimpleNamespace(content=[
                SimpleNamespace(type='text', text='Share written updates. [1]'),
                SimpleNamespace(type='text', text='Before planning meetings. [1]'),
            ]), finish_reason='COMPLETE')

    def test_dispatch_grounding_response_and_metadata(self):
        result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertFalse(result.used_fallback)
        self.assertEqual(result.provider, 'cohere')
        self.assertEqual(result.model, 'command-a-plus-05-2026')
        self.assertEqual(result.answer, 'Share written updates. [1]\nBefore planning meetings. [1]')
        payload = self.chat.call_args.kwargs
        self.assertEqual(payload['max_tokens'], 2048)
        self.assertIn('How do we plan?', payload['messages'][1]['content'])
        self.assertIn(self.passages[0]['text'], payload['messages'][1]['content'])
        self.assertIn('[1] Title: Planning', payload['messages'][1]['content'])
        self.assertEqual(generate_answer('How do we plan?', self.passages), result.answer)

    def test_history_reaches_cohere_request(self):
        history = [{'role': 'user', 'content': 'Tell me about planning.'},
                   {'role': 'assistant', 'content': 'Teams write updates. [1]'}]
        generate_answer_with_metadata('Can you expand on that?', self.passages, history=history)
        prompt = self.chat.call_args.kwargs['messages'][1]['content']
        self.assertIn('Tell me about planning.', prompt)
        self.assertIn('Teams write updates.', prompt)
        self.assertIn('Current question: Can you expand on that?', prompt)

    def test_unsupported_cohere_response_shows_matches(self):
        self.chat.return_value.message.content = [SimpleNamespace(type='text', text=UNSUPPORTED)]
        result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertFalse(result.used_fallback)
        self.assertEqual(result.answer_basis, 'general_knowledge')
        self.assertIn('General AI knowledge', result.answer)

    def test_missing_key(self):
        with patch.dict(os.environ, {'COHERE_API_KEY': ''}):
            result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertTrue(result.used_fallback)
        self.assertIn('Missing COHERE_API_KEY', result.error)
        self.factory.assert_not_called()

    def test_api_failure(self):
        self.chat.side_effect = ApiError(status_code=401, body={'message': 'Invalid token'})
        result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertTrue(result.used_fallback)
        self.assertIn('HTTP 401', result.error)

    def test_connection_failure(self):
        self.chat.side_effect = ConnectError('connection failed')
        result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertTrue(result.used_fallback)
        self.assertIn('Cohere request failed', result.error)

    def test_empty_content(self):
        self.chat.return_value.message.content = None
        result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertTrue(result.used_fallback)
        self.assertIn('no final text', result.error)

    def test_low_relevance_uses_general_knowledge_directly(self):
        result = generate_answer_with_metadata('Unrelated', [{**self.passages[0], 'score': 0.01}])
        self.assertFalse(result.used_fallback)
        self.assertEqual(result.answer_basis, 'general_knowledge')
        self.assertIn('not verified against GitLab’s handbook', result.answer)
        self.assertIn('Verify important details', result.answer)
        self.chat.assert_called_once()
        self.assertNotIn('Passage:', self.chat.call_args.kwargs['messages'][-1]['content'])

    def test_no_passages_still_generates_general_answer(self):
        result = generate_answer_with_metadata('What is an API?', [])
        self.assertEqual(result.answer_basis, 'general_knowledge')
        self.assertIn('General AI knowledge', result.answer)
        self.assertNotIn('**Closest matches**', result.answer)
        self.assertEqual(generate_answer('What is an API?', []), result.answer)

    def test_handbook_refusal_triggers_separate_general_request(self):
        def response(text):
            return SimpleNamespace(message=SimpleNamespace(content=[
                SimpleNamespace(type='text', text=text)]), finish_reason='COMPLETE')
        self.chat.side_effect = [response(UNSUPPORTED), response('In general, teams can plan asynchronously.')]
        result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertEqual(self.chat.call_count, 2)
        self.assertEqual(result.answer_basis, 'general_knowledge')
        self.assertIn('In general, teams can plan asynchronously.', result.answer)
        self.assertNotIn('**Closest matches**', result.answer)
        self.assertIn('not verified against GitLab’s handbook', result.answer)
        general_request = self.chat.call_args.kwargs['messages']
        self.assertIn('Do not invent GitLab policies', general_request[0]['content'])
        self.assertEqual(general_request[-1]['content'], 'How do we plan?')

    def test_handbook_only_preference_prevents_general_request(self):
        self.chat.return_value.message.content = [SimpleNamespace(type='text', text=UNSUPPORTED)]
        result = generate_answer_with_metadata('How do we plan?', self.passages, allow_general_knowledge=False)
        self.chat.assert_called_once()
        self.assertEqual(result.answer_basis, 'handbook')
        self.assertIn('**Closest matches**', result.answer)
        self.chat.reset_mock()
        result = generate_answer_with_metadata('What is an API?', [], allow_general_knowledge=False)
        self.chat.assert_not_called()
        self.assertEqual(result.answer_basis, 'handbook')

    def test_handbook_answer_is_distinct_from_general_knowledge(self):
        result = generate_answer_with_metadata('How do we plan?', self.passages)
        self.assertEqual(result.answer_basis, 'handbook')
        self.assertNotIn('Not verified', result.answer)
        self.chat.assert_called_once()

    def test_general_knowledge_api_failure_is_not_presented_as_success(self):
        self.chat.side_effect = ApiError(status_code=429, body={'message': 'Rate limited'})
        result = generate_answer_with_metadata('What is an API?', [])
        self.assertTrue(result.used_fallback)
        self.assertIn('HTTP 429', result.error)
        self.assertNotIn('General knowledge', result.answer)


class ClosestMatchesTests(unittest.TestCase):
    def setUp(self):
        self.passages = [
            {'title': 'Planning', 'source': 'https://example.com/planning', 'score': 0.9},
            {'title': 'Planning again', 'source': 'https://example.com/planning', 'score': 0.8},
            {'title': 'Communication', 'source': 'https://example.com/comms', 'score': 0.7},
            {'title': 'Unrelated', 'source': 'https://example.com/other', 'score': 0.01},
        ]

    def test_unsupported_links_unique_relevant_pages(self):
        answer = add_closest_matches(UNSUPPORTED, self.passages)
        self.assertIn('**Closest matches**', answer)
        self.assertEqual(answer.count('https://example.com/planning'), 1)
        self.assertIn('https://example.com/comms', answer)
        self.assertNotIn('https://example.com/other', answer)
        self.assertIn('does not directly answer your question', answer)
        self.assertIn('Please rephrase', answer)

    def test_common_no_answer_wording(self):
        for answer in ["I couldn’t find the answer in the indexed passages.",
                       "Couldn't find an answer in the provided documents."]:
            with self.subTest(answer=answer):
                self.assertIn('**Closest matches**', add_closest_matches(answer, self.passages))

    def test_successful_answer_unchanged(self):
        answer = 'Write updates before planning meetings. [1]'
        self.assertEqual(add_closest_matches(answer, self.passages), answer)

    def test_no_matches_does_not_invent_links(self):
        answer = add_closest_matches(UNSUPPORTED, [])
        self.assertNotIn('**Closest matches**', answer)
        self.assertIn('Please rephrase', answer)
