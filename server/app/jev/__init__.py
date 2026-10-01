"""JEV — deterministic layer in front of the LLM.

request → classify (regex, no LLM) → cache hit | rule | direct service call → reply
anything not handled with confidence ≥ JEV_MIN_CONFIDENCE → None → existing LLM graph, unchanged.
"""
from __future__ import annotations

import uuid
from collections import Counter

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.core.config import settings
from app.core.logging import get_logger
from app.jev import cache
from app.jev.classifier import classify
from app.jev.router import dispatch

log = get_logger("jev")

HANDLERS = ("jev_cache", "jev_rule", "jev_service")

# Process-wide request counters: handled_by -> n, plus llm_tokens. Durable numbers live in AiEvalLog.
STATS: Counter = Counter()


def _question(messages: list[BaseMessage]) -> str:
    last = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    return last.content if last is not None and isinstance(last.content, str) else ""


def _reply(text: str, handled_by: str, route: str, confidence: float) -> AIMessage:
    msg = AIMessage(content=text)
    msg.response_metadata = {"provider": handled_by, "route": route, "jev_confidence": confidence}
    return msg


async def try_handle(messages: list[BaseMessage], user_id: str, db_session,
                     collector: dict | None) -> AIMessage | None:
    """Answer deterministically or return None to fall through to the LLM."""
    if not settings.jev_enabled or db_session is None:
        return None
    intent = classify(_question(messages))
    if intent is None or intent.confidence < settings.jev_min_confidence:
        return None

    blocks = collector["blocks"] if collector is not None else []
    k = cache.key(user_id, intent.name, intent.params)
    if hit := cache.get(k):
        blocks.extend(hit.blocks)
        return _reply(hit.text, "jev_cache", hit.route, intent.confidence)

    from app.ai.tools import set_agent_context

    before = len(blocks)
    try:
        set_agent_context(db_session, uuid.UUID(user_id), collector)
        routed = await dispatch(intent)
    except Exception as exc:  # noqa: BLE001 — any JEV failure must degrade to the LLM path
        log.warning("jev_dispatch_failed", intent=intent.name, error=str(exc)[:200])
        routed = None
    if routed is None:
        del blocks[before:]  # don't leak half-built cards into the LLM turn
        return None

    cache.put(k, routed.text, blocks[before:], routed.handled_by, routed.route,
              settings.jev_cache_ttl_seconds)
    return _reply(routed.text, routed.handled_by, routed.route, intent.confidence)


def record_request(handled_by: str, latency_ms: int, llm_tokens: int) -> None:
    """One log line per chat turn; counters make LLM-call reduction measurable."""
    kind = handled_by if handled_by in HANDLERS else "llm"
    STATS[kind] += 1
    STATS["llm_tokens"] += llm_tokens
    jev = sum(STATS[h] for h in HANDLERS)
    total = jev + STATS["llm"]
    log.info("jev_request", handled_by=kind, provider=handled_by, latency_ms=latency_ms,
             llm_tokens=llm_tokens, jev_total=jev, llm_total=STATS["llm"],
             llm_calls_avoided_pct=round(jev / total * 100, 1) if total else 0.0)
