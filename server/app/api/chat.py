from __future__ import annotations

import time as _time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graph import run_chat
from app.ai.pii import mask_pii
from app.ai.tools import new_collector
from app.db.session import get_db
from app.models import ChatMessage, ChatThread, User
from app.services import chat_service
from app.services.chat_service import SendIn
from app.services.deps import get_current_user

router = APIRouter(prefix="/chat", tags=["ai"])


class MessageOut(BaseModel):
    id: uuid.UUID | None = None
    role: str
    content: str
    provider: str | None = None
    created_at: object | None = None
    blocks: list[dict] = []
    actions: list[dict] = []


class ThreadPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    pinned: bool | None = None


class ActionDecision(BaseModel):
    decision: str = Field(pattern="^(confirm|cancel)$")


def _thread_out(t: ChatThread, preview: str | None = None, pending: int = 0) -> dict:
    return {
        "id": str(t.id),
        "title": t.title,
        "agent_mode": t.agent_mode,
        "source_tab": t.source_tab,
        "context": t.context,
        "pinned": bool(t.pinned),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "preview": preview,
        "pending_actions": pending,
    }


@router.get("/threads")
async def list_threads(
    q: str | None = Query(default=None, max_length=200),
    source_tab: str | None = Query(default=None, max_length=40),
    since: datetime | None = None,
    until: datetime | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ChatThread).where(ChatThread.user_id == user.id, ChatThread.archived.is_(False))
    if source_tab:
        stmt = stmt.where(ChatThread.source_tab == source_tab)
    if since:
        stmt = stmt.where(ChatThread.updated_at >= since)
    if until:
        stmt = stmt.where(ChatThread.updated_at <= until)
    if q:
        like = f"%{q.lower()}%"
        matching = select(ChatMessage.thread_id).where(func.lower(ChatMessage.content).like(like))
        stmt = stmt.where(or_(func.lower(ChatThread.title).like(like), ChatThread.id.in_(matching)))
    rows = (await db.execute(
        stmt.order_by(ChatThread.pinned.desc(), ChatThread.updated_at.desc()).limit(100))).scalars().all()

    out = []
    for t in rows:
        # ponytail: one query per thread (max 100); batch with a window query if the hub gets slow.
        last = (await db.execute(
            select(ChatMessage).where(ChatMessage.thread_id == t.id)
            .order_by(ChatMessage.created_at.desc()).limit(20))).scalars().all()
        pending = sum(1 for m in last for a in (m.tool_calls or {}).get("actions", [])
                      if a.get("status") == "pending")
        preview = last[0].content[:140] if last else None
        out.append(_thread_out(t, preview, pending))
    return out


@router.patch("/threads/{thread_id}")
async def update_thread(
    thread_id: uuid.UUID,
    body: ThreadPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread = await db.scalar(select(ChatThread).where(
        ChatThread.id == thread_id, ChatThread.user_id == user.id, ChatThread.archived.is_(False)))
    if not thread:
        raise HTTPException(404, "Thread not found")
    if body.title is not None:
        thread.title = mask_pii(body.title.strip())[:300]
    if body.pinned is not None:
        thread.pinned = body.pinned
    await db.flush()
    return _thread_out(thread)


@router.post("/send", response_model=dict)
async def send(
    body: SendIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    turn = await chat_service.begin_turn(db, user, body)
    if turn.blocked:
        await db.commit()
        return turn.blocked

    collector = new_collector()
    started = _time.perf_counter()
    reply = await run_chat(
        turn.lc_messages,
        str(user.id),
        str(turn.thread.id),
        body.agent_mode,
        page_context=body.page_context,
        db_session=db,
        page_summary=body.page_summary,
        collector=collector,
    )
    latency_ms = int((_time.perf_counter() - started) * 1000)
    result = await chat_service.complete_turn(db, user, body, turn, reply, latency_ms, collector)
    await db.commit()
    return result


@router.get("/threads/{thread_id}/messages", response_model=list[MessageOut])
async def messages(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread = await db.scalar(
        select(ChatThread).where(
            ChatThread.id == thread_id, ChatThread.user_id == user.id
        )
    )
    if not thread:
        raise HTTPException(404, "Thread not found")
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at)
        )
    ).scalars().all()
    return [chat_service.message_out(m) for m in rows]


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread = await db.scalar(
        select(ChatThread).where(
            ChatThread.id == thread_id, ChatThread.user_id == user.id
        )
    )
    if thread:
        thread.archived = True
        await db.commit()
    return None


# ── AI action proposals (never applied without explicit confirmation) ──

@router.get("/actions")
async def list_actions(
    status: str = Query(default="pending", pattern="^pending$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await chat_service.pending_actions(db, user)


@router.post("/actions/{message_id}/{action_id}")
async def decide_action(
    message_id: uuid.UUID,
    action_id: str,
    body: ActionDecision,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await chat_service.decide_action(db, user, message_id, action_id[:40], body.decision)
    await db.commit()
    return action


# ── Natural-language expense quick-add ──────────────────────────────────

@router.post("/expenses/parse")
async def parse_expense(body: dict, user: User = Depends(get_current_user)):
    """Parse free text / voice transcript into a structured expense draft."""
    from datetime import date as date_type

    text = mask_pii(str(body.get("text", ""))[:500])
    currency = str(body.get("currency", "USD")).upper()
    today = date_type.today().isoformat()

    try:
        from app.ai.llm_router import complete_json

        result = await complete_json(
            f"Extract an expense from this note. Today is {today}.\n"
            f"Default currency: {currency}\nNote: \"{text}\"\n"
            "Reply JSON only:\n"
            '{"amount_minor": int|null, "currency": str, "merchant": str, '
            '"date": "YYYY-MM-DD"|null, "category_guess": str|null,\n'
            ' "items": [{"label": str, "amount_minor": int}]|null, "confidence": float}',
            system="You extract structured expenses. If no amount is present use null.",
        )
    except Exception:
        result = None

    if not result:
        # deterministic fallback parser: "$12.40 at Starbucks"
        import re

        m = re.search(r"\$?\s*(\d+(?:[.,]\d{1,2})?)", text)
        merchant = re.search(r"(?:at|from|in|@)\s+([A-Za-z0-9&' ]{2,40})", text)
        result = {
            "amount_minor": round(float(m.group(1).replace(",", ".")) * 100) if m else None,
            "currency": currency,
            "merchant": merchant.group(1).strip() if merchant else text.strip()[:40],
            "date": today,
            "category_guess": None,
            "items": None,
            "confidence": 0.3,
        }
    return result
