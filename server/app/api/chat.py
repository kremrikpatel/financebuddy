from __future__ import annotations

import time as _time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graph import route_of, run_chat
from app.ai.guardrails import chat_rate_limiter, check_guardrails
from app.ai.pii import mask_pii
from app.core.config import settings
from app.db.session import get_db
from app.models import ChatMessage, ChatThread, User
from app.models.ai import AiEvalLog
from app.services.deps import get_current_user

router = APIRouter(prefix="/chat", tags=["ai"])


class SendIn(BaseModel):
    thread_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=8000)
    agent_mode: str = "auto"
    page_context: str | None = None


class MessageOut(BaseModel):
    role: str
    content: str
    provider: str | None = None
    created_at: object | None = None

    model_config = {"from_attributes": True}


@router.get("/threads")
async def list_threads(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    rows = (
        await db.execute(
            select(ChatThread)
            .where(ChatThread.user_id == user.id, ChatThread.archived.is_(False))
            .order_by(ChatThread.updated_at.desc())
            .limit(50)
        )
    ).scalars().all()
    return [{"id": t.id.__str__(), "title": t.title, "agent_mode": t.agent_mode} for t in rows]


@router.post("/send", response_model=dict)
async def send(
    body: SendIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate non-empty, non-whitespace message
    if not body.message or not body.message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message cannot be empty or whitespace only",
        )

    # 1. Enforce sliding-window rate limit (max 30 requests/minute per user)
    chat_rate_limiter.enforce_rate_limit(user.id)

    # 2. Content filter: Guardrails check (prompt injection & non-financial redirection)
    guardrail = check_guardrails(body.message)
    if not guardrail.allowed:
        # Create thread if not provided
        if body.thread_id:
            thread = await db.scalar(
                select(ChatThread).where(
                    ChatThread.id == body.thread_id, ChatThread.user_id == user.id
                )
            )
            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")
        else:
            masked_title = mask_pii(body.message)
            thread = ChatThread(
                user_id=user.id,
                title=masked_title[:60] + ("…" if len(masked_title) > 60 else ""),
                agent_mode=body.agent_mode,
            )
            db.add(thread)
            await db.flush()

        masked_user_content = mask_pii(body.message)
        user_msg = ChatMessage(
            thread_id=thread.id,
            role="user",
            content=masked_user_content,
        )
        reply_content = (
            guardrail.redirection_message
            or "I am FinanceBuddy, your personal finance coach. Please ask a financial question."
        )
        assistant_msg = ChatMessage(
            thread_id=thread.id,
            role="assistant",
            content=reply_content,
            provider="guardrails",
            latency_ms=5,
        )
        db.add_all([user_msg, assistant_msg])
        await db.flush()

        # Log AI Evaluation entry
        eval_log = AiEvalLog(
            user_id=user.id,
            thread_id=thread.id,
            message_id=assistant_msg.id,
            provider_used="guardrails",
            model_name="rule-guardrails-filter",
            tokens_in=len(body.message.split()),
            tokens_out=len(reply_content.split()),
            latency_ms=5,
            route_chosen=route_of(body.agent_mode, body.message, page_context=body.page_context),
            confidence_score=1.0,
            pii_fields_masked=0,
            query_summary=masked_user_content[:120],
        )
        db.add(eval_log)
        await db.commit()

        return {
            "thread_id": str(thread.id),
            "reply": {
                "role": "assistant",
                "content": reply_content,
                "provider": "guardrails",
                "latency_ms": 5,
            },
        }

    # 3. Thread lookup or initialization
    if body.thread_id:
        thread = await db.scalar(
            select(ChatThread).where(
                ChatThread.id == body.thread_id, ChatThread.user_id == user.id
            )
        )
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
    else:
        masked_title = mask_pii(body.message)
        thread = ChatThread(
            user_id=user.id,
            title=masked_title[:60] + ("…" if len(masked_title) > 60 else ""),
            agent_mode=body.agent_mode,
        )
        db.add(thread)
        await db.flush()

    # 4. PII Redaction & Metrics
    raw_message = body.message
    masked_message = mask_pii(raw_message)
    pii_count = (
        raw_message.count("@") - masked_message.count("@")
        + (1 if "[CARD" in masked_message else 0)
        + (1 if "[PHONE" in masked_message else 0)
        + (1 if "[SSN" in masked_message or "[TFN" in masked_message else 0)
        + (1 if "[EMAIL" in masked_message else 0)
        + (1 if "[IBAN" in masked_message else 0)
        + (1 if "[ACCOUNT" in masked_message else 0)
    )
    pii_count = max(0, pii_count)
    if masked_message != raw_message and pii_count == 0:
        pii_count = 1

    user_msg = ChatMessage(
        thread_id=thread.id,
        role="user",
        content=masked_message,
    )
    db.add(user_msg)

    # 5. Fetch previous thread history
    history = list(
        (
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.thread_id == thread.id)
                .order_by(ChatMessage.created_at)
                .limit(30)
            )
        )
        .scalars()
        .all()
    )

    lc_messages = [
        HumanMessage(content=m.content) if m.role == "user" else AIMessage(content=m.content)
        for m in history
    ]
    lc_messages.append(HumanMessage(content=user_msg.content))

    # 6. Execute AI conversation flow
    started = _time.perf_counter()
    reply = await run_chat(
        lc_messages,
        str(user.id),
        str(thread.id),
        body.agent_mode,
        page_context=body.page_context,
        db_session=db,
    )
    latency_ms = int((_time.perf_counter() - started) * 1000)

    provider = (reply.response_metadata or {}).get("provider") or (
        (getattr(reply, "response_metadata", {}) or {}).get("llm_output", {}) or {}
    ).get("provider") or "mock_openai"

    route_meta = (reply.response_metadata or {}).get("route")
    if route_meta and route_meta in ("coach", "budget", "fraud", "goals", "tax", "assistant"):
        route_chosen = route_meta
    elif body.agent_mode and body.agent_mode != "auto":
        route_chosen = body.agent_mode
    else:
        route_chosen = route_of(body.agent_mode, body.message, page_context=body.page_context)

    assistant_msg = ChatMessage(
        thread_id=thread.id,
        role="assistant",
        content=reply.content,
        provider=provider,
        latency_ms=latency_ms,
    )
    db.add(assistant_msg)
    await db.flush()

    # 7. Record AI Evaluation Metric
    eval_log = AiEvalLog(
        user_id=user.id,
        thread_id=thread.id,
        message_id=assistant_msg.id,
        provider_used=provider,
        model_name=settings.llm_primary_model,
        tokens_in=max(1, len(user_msg.content.split()) * 2),
        tokens_out=max(1, len(reply.content.split()) * 2),
        latency_ms=latency_ms,
        route_chosen=route_chosen,
        confidence_score=0.95,
        pii_fields_masked=pii_count,
        query_summary=masked_message[:120],
    )
    db.add(eval_log)
    await db.commit()

    return {
        "thread_id": str(thread.id),
        "reply": {
            "role": "assistant",
            "content": reply.content,
            "provider": provider,
            "latency_ms": latency_ms,
        },
    }


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
    return rows


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
