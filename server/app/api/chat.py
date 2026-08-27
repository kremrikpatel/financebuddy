from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graph import run_chat
from app.ai.pii import mask_pii
from app.db.session import get_db
from app.models import ChatMessage, ChatThread, User
from app.services.deps import get_current_user

router = APIRouter(prefix="/chat", tags=["ai"])


class SendIn(BaseModel):
    thread_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=8000)
    agent_mode: str = "auto"


class MessageOut(BaseModel):
    role: str
    content: str
    provider: str | None = None
    created_at: object | None = None

    model_config = {"from_attributes": True}


@router.get("/threads")
async def list_threads(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(ChatThread).where(ChatThread.user_id == user.id, ChatThread.archived.is_(False))
        .order_by(ChatThread.updated_at.desc()).limit(50))).scalars().all()
    return [{"id": t.id.__str__(), "title": t.title, "agent_mode": t.agent_mode} for t in rows]


@router.post("/send", response_model=dict)
async def send(body: SendIn, user: User = Depends(get_current_user),
               db: AsyncSession = Depends(get_db)):
    if body.thread_id:
        thread = await db.scalar(select(ChatThread).where(
            ChatThread.id == body.thread_id, ChatThread.user_id == user.id))
        if not thread:
            raise HTTPException(404, "Thread not found")
    else:
        thread = ChatThread(user_id=user.id,
                            title=body.message[:60] + ("…" if len(body.message) > 60 else ""),
                            agent_mode=body.agent_mode)
        db.add(thread)
        await db.flush()

    history = list((await db.execute(
        select(ChatMessage).where(ChatMessage.thread_id == thread.id)
        .order_by(ChatMessage.created_at).limit(30))).scalars().all())

    user_msg = ChatMessage(thread_id=thread.id, role="user",
                           content=mask_pii(body.message))
    db.add(user_msg)

    lc_messages = [HumanMessage(content=m.content) if m.role == "user" else AIMessage(content=m.content)
                   for m in history]
    lc_messages.append(HumanMessage(content=user_msg.content))

    import time as _time

    started = _time.perf_counter()
    reply = await run_chat(lc_messages, str(user.id), str(thread.id),
                           body.agent_mode, db_session=db)
    latency_ms = int((_time.perf_counter() - started) * 1000)

    provider = (reply.response_metadata or {}).get("provider") or \
               ((getattr(reply, "response_metadata", {}) or {}).get("llm_output", {}) or {}).get("provider")

    assistant_msg = ChatMessage(thread_id=thread.id, role="assistant",
                                content=reply.content, provider=provider,
                                latency_ms=latency_ms)
    db.add(assistant_msg)
    await db.flush()
    return {
        "thread_id": str(thread.id),
        "reply": {"role": "assistant", "content": reply.content,
                  "provider": provider, "latency_ms": latency_ms},
    }


@router.get("/threads/{thread_id}/messages", response_model=list[MessageOut])
async def messages(thread_id: uuid.UUID, user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    thread = await db.scalar(select(ChatThread).where(
        ChatThread.id == thread_id, ChatThread.user_id == user.id))
    if not thread:
        raise HTTPException(404, "Thread not found")
    rows = (await db.execute(
        select(ChatMessage).where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at))).scalars().all()
    return rows


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: uuid.UUID, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    thread = await db.scalar(select(ChatThread).where(
        ChatThread.id == thread_id, ChatThread.user_id == user.id))
    if thread:
        thread.archived = True
    return None


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
            f'Extract an expense from this note. Today is {today}.\n'
            f'Default currency: {currency}\nNote: "{text}"\n'
            'Reply JSON only:\n'
            '{"amount_minor": int|null, "currency": str, "merchant": str, '
            '"date": "YYYY-MM-DD"|null, "category_guess": str|null,\n'
            ' "items": [{"label": str, "amount_minor": int}]|null, "confidence": float}',
            system="You extract structured expenses. If no amount is present use null.")
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
            "date": today, "category_guess": None, "items": None, "confidence": 0.3,
        }
    return result
