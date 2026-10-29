from __future__ import annotations


def select_passages(candidates: list[dict], top_k: int, strategy: str = 'similarity') -> list[dict]:
    """Keep similarity order, optionally preventing one page from filling the answer."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if strategy == 'similarity':
        return candidates[:top_k]
    if strategy != 'source_diversity':
        raise ValueError(f'Unknown retrieval strategy: {strategy}')
    selected = []
    seen = set()
    for passage in candidates:
        source = passage['source'].rstrip('/')
        if source in seen:
            continue
        seen.add(source)
        selected.append(passage)
        if len(selected) >= top_k:
            break
    return selected
