from __future__ import annotations

import re

HISTORY_EXCHANGES = 3


def recent_history(messages: list[dict] | None) -> list[dict]:
    """Keep only the last three exchanges, without UI metadata or system roles."""
    history = [
        {'role': message['role'], 'content': message['content'][:2000]}
        for message in (messages or [])
        if message.get('role') in {'user', 'assistant'}
        and isinstance(message.get('content'), str) and message['content'].strip()
    ]
    return history[-HISTORY_EXCHANGES * 2:]


def retrieval_question(question: str, messages: list[dict] | None) -> str:
    """Give short follow-ups their recent topic without changing standalone queries."""
    history = recent_history(messages)
    follow_up = re.search(
        r"\b(it|its|they|their|them|that|those|this|these|above|previous|more|elaborate)\b"
        r"|^(and|what about|how about|why|can you expand|give an example)\b",
        question.lower(),
    )
    if not history or not follow_up:
        return question
    topics = [message['content'] for message in history if message['role'] == 'user']
    if not topics:
        return question
    return '\n'.join([*topics, question])
