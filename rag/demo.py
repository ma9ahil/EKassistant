"""Public demo limits. Counts survive New conversation, but not new browser sessions."""
from __future__ import annotations

import os
import threading
import time


def demo_mode() -> bool:
    return os.getenv('DEMO_MODE', 'true').lower() in {'true', '1', 'yes'}


def question_limit() -> int:
    return max(1, int(os.getenv('DEMO_SESSION_QUESTIONS', '5')))


def admit_question(state, now: float | None = None) -> str | None:
    if not demo_mode():
        return None
    now = time.monotonic() if now is None else now
    if state.get('demo_questions', 0) >= question_limit():
        return 'You’ve reached the demo’s question limit. You can still review this conversation and its sources.'
    cooldown = max(0, int(os.getenv('DEMO_COOLDOWN_SECONDS', '10')))
    previous = state.get('demo_last_question')
    if previous is not None and now - previous < cooldown:
        return f'Please wait {max(1, int(cooldown - (now - previous)) + 1)} seconds before asking again.'
    state['demo_questions'] = state.get('demo_questions', 0) + 1
    state['demo_last_question'] = now
    return None


class DemoBudgetExceeded(RuntimeError):
    pass


_budget_lock = threading.Lock()
_api_calls = 0


def reserve_api_call() -> None:
    """Shared safety cap across browser sessions, for this server process."""
    global _api_calls
    if not demo_mode():
        return
    with _budget_lock:
        if _api_calls >= max(1, int(os.getenv('DEMO_SERVER_API_CALLS', '50'))):
            raise DemoBudgetExceeded('The public demo has reached its AI usage limit. Handbook excerpts are still available.')
        _api_calls += 1
