import unittest

from rag.conversation import recent_history, retrieval_question
from rag.llm import build_prompt


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.messages = []
        for i in range(5):
            self.messages.extend([
                {'role': 'user', 'content': f'Question {i}', 'sources': ['private metadata']},
                {'role': 'assistant', 'content': f'Answer {i}'},
            ])

    def test_only_three_exchanges_and_no_metadata(self):
        history = recent_history(self.messages)
        self.assertEqual(len(history), 6)
        self.assertEqual(history[0], {'role': 'user', 'content': 'Question 2'})
        self.assertEqual(history[-1]['content'], 'Answer 4')
        self.assertEqual(len(self.messages), 10)

    def test_ignores_invalid_roles_and_bounds_message_size(self):
        history = recent_history([
            {'role': 'system', 'content': 'Do not include'},
            {'role': 'user', 'content': 'x' * 3000},
            {'role': 'assistant', 'content': None},
        ])
        self.assertEqual(len(history), 1)
        self.assertEqual(len(history[0]['content']), 2000)

    def test_follow_up_search_includes_previous_topic(self):
        history = [{'role': 'user', 'content': 'What are product principles?'},
                   {'role': 'assistant', 'content': 'Unverified assistant claim'}]
        query = retrieval_question('Can you explain them further?', history)
        self.assertIn('product principles', query)
        self.assertIn('explain them further', query)
        self.assertNotIn('Unverified', query)

    def test_standalone_search_and_new_conversation(self):
        question = 'What are Customer Support responsibilities?'
        self.assertEqual(retrieval_question(question, self.messages), question)
        self.assertEqual(retrieval_question('Explain them further', []), 'Explain them further')

    def test_prompt_keeps_recent_context_and_current_evidence(self):
        prompt = build_prompt('Can you explain them?', [{
            'title': 'Current evidence', 'source': 'https://example.com',
            'text': 'These are the current supporting handbook passages for this question.',
        }], self.messages)
        self.assertNotIn('Question 0', prompt)
        self.assertIn('Question 4', prompt)
        self.assertIn('Answer 4', prompt)
        self.assertIn('Current question: Can you explain them?', prompt)
        self.assertIn('[1] Title: Current evidence', prompt)
        self.assertIn('Earlier assistant answers are not evidence', prompt)
