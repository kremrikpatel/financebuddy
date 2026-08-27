"""WebSocket: real-time notifications + live chat streaming channel."""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.services.events import bus, ws_manager

router = APIRouter()


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
    try:
        # bridge event-bus → websocket while also handling pings
        async def pump():
            while True:
                msg = await queue.get()
                await ws.send_json(msg)

        receiver = asyncio.create_task(ws.receive_text())
        sender = asyncio.create_task(pump())
        done, pending = await asyncio.wait(
            {receiver, sender}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await bus.unsubscribe(user_id, queue)
        ws_manager.disconnect(ws, user_id)
