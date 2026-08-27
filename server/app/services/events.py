"""Real-time event pipeline.

Producer: any service publishes domain events to a Redis Stream.
Consumer: workers.event_consumer processes them (anomaly scan, alerts) and
the in-process ConnectionManager fans notifications out over WebSocket.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("events")

STREAM = "fb:events"
GROUP = "fb-workers"
DLQ = "fb:events:dlq"


def new_event(event_type: str, user_id: str | None = None, payload: dict | None = None) -> dict:
    return {
        "id": uuid.uuid4().hex,
        "type": event_type,
        "user_id": str(user_id or ""),
        "ts": str(time.time()),
        "payload": json.dumps(payload or {}, default=str),
    }


class EventBus:
    """Publishes to Redis Streams; falls back to an in-process queue when
    Redis is unavailable so local dev never blocks on infra."""

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._local: asyncio.Queue[dict] = asyncio.Queue()
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        try:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await self._redis.ping()
            try:
                await self._redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
            except Exception:
                pass  # group exists
            log.info("event_bus_connected", backend="redis")
        except Exception as exc:
            self._redis = None
            log.warning("event_bus_local_fallback", error=str(exc))

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    async def publish(self, event: dict) -> None:
        if self._redis:
            try:
                await self._redis.xadd(STREAM, event)
                return
            except Exception as exc:
                log.error("publish_failed_falling_back", error=str(exc))
                self._redis = None
        await self._local.put(event)

    async def read_batch(self, count: int = 20, block_ms: int = 5000) -> list[tuple[str, dict]]:
        if not self._redis:
            try:
                evt = await asyncio.wait_for(self._local.get(), timeout=block_ms / 1000)
                return [("local", evt)]
            except TimeoutError:
                return []
        resp = await self._redis.xreadgroup(GROUP, "consumer-1", {STREAM: ">"}, count=count, block=block_ms)
        out: list[tuple[str, dict]] = []
        for _stream, entries in resp:
            for entry_id, fields in entries:
                out.append((entry_id, fields))
        return out

    async def ack(self, entry_id: str) -> None:
        if self._redis:
            try:
                await self._redis.xack(STREAM, GROUP, entry_id)
            except Exception as exc:
                log.warning("ack_failed", error=str(exc))

    # ── WebSocket fan-out ──────────────────────────────────────────────
    async def subscribe(self, user_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.setdefault(user_id, set()).add(q)
        return q

    async def unsubscribe(self, user_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.get(user_id, set()).discard(q)

    async def notify_user(self, user_id: str, message: dict) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(str(user_id), ()))
        for q in queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("ws_queue_overflow", user=user_id)


bus = EventBus()


@dataclass
class WSManager:
    connections: dict[str, set[WebSocket]] = field(default_factory=dict)

    async def connect(self, ws: WebSocket, user_id: str) -> None:
        from fastapi import WebSocketDisconnect  # noqa: F401

        await ws.accept()
        self.connections.setdefault(user_id, set()).add(ws)

    def disconnect(self, ws: WebSocket, user_id: str) -> None:
        self.connections.get(user_id, set()).discard(ws)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        for ws in list(self.connections.get(str(user_id), ())):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws, str(user_id))


ws_manager = WSManager()
