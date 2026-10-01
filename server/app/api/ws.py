"""WebSocket: real-time notifications + live chat streaming on the same connection.

Server → client frames
  (unchanged) notification/alert payloads from the event bus
  {"type": "pong"}
  {"type": "chat.started",   "request_id", "thread_id"}
  {"type": "chat.delta",     "request_id", "text"}
  {"type": "chat.tool",      "request_id", "name"}
  {"type": "chat.done",      "request_id", "thread_id", "reply": {...message}}
  {"type": "chat.cancelled", "request_id"}
  {"type": "chat.error",     "request_id", "code", "detail"}

Client → server frames
  {"type": "ping"}
  {"type": "chat.send", "request_id", "thread_id"?, "message", "agent_mode"?, "page_context"?, "page_summary"?}
  {"type": "chat.cancel", "request_id"}
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import suppress

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.ai.graph import stream_chat
from app.ai.tools import new_collector
from app.core.logging import get_logger
from app.core.security import decode_token
from app.db.session import SessionFactory
from app.models import User
from app.services import chat_service
from app.services.chat_service import SendIn
from app.services.events import bus, ws_manager

router = APIRouter()
log = get_logger("ws")

MAX_CONCURRENT_CHATS = 2
SEND_FIELDS = ("thread_id", "message", "agent_mode", "page_context", "page_summary")


async def _stream_turn(send, user_id: str, request_id: str, frame: dict) -> None:
    try:
        body = SendIn.model_validate({k: frame[k] for k in SEND_FIELDS if frame.get(k) is not None})
    except ValidationError:
        await send({"type": "chat.error", "request_id": request_id, "code": 422, "detail": "Invalid message"})
        return

    async with SessionFactory() as db:
        try:
            user = await db.get(User, uuid.UUID(user_id))
            if not user or not getattr(user, "is_active", True):
                raise HTTPException(401, "Not authenticated")
            turn = await chat_service.begin_turn(db, user, body)
            if turn.blocked:
                await db.commit()
                await send({"type": "chat.done", "request_id": request_id, **turn.blocked})
                return
            # Persist the thread and (masked) question first, so a stopped reply keeps the question.
            await db.commit()
            await send({"type": "chat.started", "request_id": request_id, "thread_id": str(turn.thread.id)})

            collector = new_collector()
            started = time.perf_counter()
            final = None
            async for ev in stream_chat(
                turn.lc_messages, str(user.id), str(turn.thread.id), body.agent_mode,
                page_context=body.page_context, db_session=db,
                page_summary=body.page_summary, collector=collector,
            ):
                if ev["type"] == "delta":
                    await send({"type": "chat.delta", "request_id": request_id, "text": ev["text"]})
                elif ev["type"] == "tool":
                    await send({"type": "chat.tool", "request_id": request_id, "name": ev["name"]})
                else:
                    final = ev["message"]
            latency_ms = int((time.perf_counter() - started) * 1000)
            result = await chat_service.complete_turn(db, user, body, turn, final, latency_ms, collector)
            await db.commit()
            await send({"type": "chat.done", "request_id": request_id, **result})
        except asyncio.CancelledError:
            await db.rollback()
            with suppress(Exception):
                await send({"type": "chat.cancelled", "request_id": request_id})
            raise
        except HTTPException as exc:
            await db.rollback()
            detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
            await send({"type": "chat.error", "request_id": request_id, "code": exc.status_code, "detail": detail})
        except Exception as exc:  # noqa: BLE001 — surface a clean error frame, keep the socket alive
            log.warning("ws_chat_failed", error=str(exc)[:200])
            await db.rollback()
            await send({"type": "chat.error", "request_id": request_id, "code": 500,
                        "detail": "The AI engine is temporarily unavailable."})


@router.websocket("/ws/notifications")
async def notifications(ws: WebSocket, token: str = Query(...)):
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        user_id = payload["sub"]
    except Exception:
        await ws.close(code=4001)
        return

    queue = await bus.subscribe(user_id)
    await ws_manager.connect(ws, user_id)
    send_lock = asyncio.Lock()
    chats: dict[str, asyncio.Task] = {}

    async def send(msg: dict) -> None:
        async with send_lock:
            await ws.send_json(msg)

    async def pump() -> None:
        # bridge event-bus → websocket
        while True:
            await send(await queue.get())

    sender = asyncio.create_task(pump())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                frame = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(frame, dict):
                continue
            kind = frame.get("type")
            if kind == "ping":
                await send({"type": "pong"})
            elif kind == "chat.send":
                request_id = str(frame.get("request_id") or uuid.uuid4())[:64]
                if request_id in chats or len(chats) >= MAX_CONCURRENT_CHATS:
                    await send({"type": "chat.error", "request_id": request_id, "code": 429,
                                "detail": "Another reply is still in progress."})
                    continue
                task = asyncio.create_task(_stream_turn(send, user_id, request_id, frame))
                chats[request_id] = task
                task.add_done_callback(lambda _t, rid=request_id: chats.pop(rid, None))
            elif kind == "chat.cancel":
                task = chats.get(str(frame.get("request_id")))
                if task:
                    task.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        sender.cancel()
        for task in list(chats.values()):
            task.cancel()
        await bus.unsubscribe(user_id, queue)
        ws_manager.disconnect(ws, user_id)
