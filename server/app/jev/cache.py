"""Short-circuit cache for JEV answers (never LLM answers).

Key: (user_id, intent, params). Entries expire after a TTL and are dropped as soon as the
user's financial data changes: any write bumps that user's generation counter, and an entry
from an older generation is a miss.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

MAX_ENTRIES = 5000


@dataclass(frozen=True)
class Entry:
    generation: int
    expires_at: float
    text: str
    blocks: tuple
    handled_by: str
    route: str


# ponytail: per-process dict; move to Redis (already a dependency) when running >1 API worker.
_store: dict[tuple, Entry] = {}
_generation: dict[str, int] = {}


def key(user_id: str, intent: str, params: dict) -> tuple:
    return (str(user_id), intent, tuple(sorted(params.items())))


def get(k: tuple) -> Entry | None:
    e = _store.get(k)
    if e is None:
        return None
    if e.expires_at < time.monotonic() or e.generation != _generation.get(k[0], 0):
        _store.pop(k, None)
        return None
    return e


def put(k: tuple, text: str, blocks: list, handled_by: str, route: str, ttl_seconds: int) -> None:
    if len(_store) >= MAX_ENTRIES:
        _store.clear()  # ponytail: crude bound; LRU if hit rates matter at this size
    _store[k] = Entry(_generation.get(k[0], 0), time.monotonic() + ttl_seconds,
                      text, tuple(blocks), handled_by, route)


def invalidate(user_id: str | None) -> None:
    """Called whenever a user's financial data may have changed."""
    if user_id:
        uid = str(user_id)
        _generation[uid] = _generation.get(uid, 0) + 1


def clear() -> None:
    _store.clear()
    _generation.clear()
