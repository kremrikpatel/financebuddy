"""Chat turn orchestration shared by HTTP `/chat/send` and the WebSocket stream.

One code path for rate limiting, guardrails, PII masking, persistence and eval logging,
so the streaming and non-streaming transports cannot drift apart.

Action proposals produced by the agent are stored on the assistant message
(`ChatMessage.tool_calls["actions"]`) with status "pending". Nothing is applied until
`decide_action(..., "confirm")` runs from an explicit user confirmation.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app import jev
from app.ai.graph import route_of
from app.ai.guardrails import chat_rate_limiter, check_guardrails
from app.ai.pii import mask_pii
from app.core.config import settings
from app.db.base import utcnow
from app.models import Budget, BudgetEnvelope, Category, ChatMessage, ChatThread, Goal, Transaction, User
from app.models.ai import AiEvalLog

MAX_PAGE_SUMMARY_BYTES = 4000
KNOWN_TABS = {"dashboard", "transactions", "budgets", "goals", "debts", "coach", "family", "tax",
              "connections", "ai-eval", "settings"}
ROUTE_NAMES = ("coach", "budget", "fraud", "goals", "tax", "assistant")


class SendIn(BaseModel):
    thread_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=8000)
    agent_mode: str = "auto"
    page_context: str | None = Field(default=None, max_length=300)
    page_summary: dict | None = None

    @field_validator("page_summary")
    @classmethod
    def _bounded_summary(cls, v: dict | None) -> dict | None:
        if v is not None and len(json.dumps(v, default=str)) > MAX_PAGE_SUMMARY_BYTES:
            raise ValueError(f"page_summary must be at most {MAX_PAGE_SUMMARY_BYTES} bytes")
        return v


def source_tab_of(page_context: str | None) -> str | None:
    if page_context is None:
        return None
    first = page_context.split("?")[0].strip("/").split("/")[0].lower()
    tab = first or "dashboard"
    return tab if tab in KNOWN_TABS else None


def message_out(m: ChatMessage) -> dict:
    extra = m.tool_calls or {}
    return {
        "id": str(m.id),
        "role": m.role,
        "content": m.content,
        "provider": m.provider,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "blocks": extra.get("blocks", []),
        "actions": extra.get("actions", []),
    }


@dataclass
class Turn:
    thread: ChatThread
    masked_message: str
    pii_count: int = 0
    lc_messages: list[BaseMessage] = field(default_factory=list)
    blocked: dict | None = None  # finished guardrail response, when the message was redirected


async def _thread_for(db: AsyncSession, user: User, body: SendIn) -> ChatThread:
    if body.thread_id:
        thread = await db.scalar(select(ChatThread).where(
            ChatThread.id == body.thread_id, ChatThread.user_id == user.id))
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread
    masked_title = mask_pii(body.message)
    thread = ChatThread(
        user_id=user.id,
        title=masked_title[:60] + ("…" if len(masked_title) > 60 else ""),
        agent_mode=body.agent_mode,
        source_tab=source_tab_of(body.page_context),
        context={"path": body.page_context, "summary": body.page_summary} if body.page_context else None,
    )
    db.add(thread)
    await db.flush()
    return thread


async def begin_turn(db: AsyncSession, user: User, body: SendIn) -> Turn:
    """Validate, rate-limit, guardrail, persist the (masked) user message and build history."""
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Message cannot be empty or whitespace only")

    chat_rate_limiter.enforce_rate_limit(user.id)

    guardrail = check_guardrails(body.message)
    thread = await _thread_for(db, user, body)

    if not guardrail.allowed:
        masked_user_content = mask_pii(body.message)
        user_msg = ChatMessage(thread_id=thread.id, role="user", content=masked_user_content)
        reply_content = (
            guardrail.redirection_message
            or "I am FinanceBuddy, your personal finance coach. Please ask a financial question."
        )
        assistant_msg = ChatMessage(thread_id=thread.id, role="assistant", content=reply_content,
                                    provider="guardrails", latency_ms=5)
        db.add_all([user_msg, assistant_msg])
        await db.flush()
        db.add(AiEvalLog(
            user_id=user.id, thread_id=thread.id, message_id=assistant_msg.id,
            provider_used="guardrails", model_name="rule-guardrails-filter",
            tokens_in=len(body.message.split()), tokens_out=len(reply_content.split()),
            latency_ms=5,
            route_chosen=route_of(body.agent_mode, body.message, page_context=body.page_context),
            confidence_score=1.0, pii_fields_masked=0, query_summary=masked_user_content[:120],
        ))
        thread.updated_at = utcnow()
        await db.flush()
        return Turn(thread=thread, masked_message=masked_user_content, blocked={
            "thread_id": str(thread.id),
            "reply": {"role": "assistant", "content": reply_content, "provider": "guardrails",
                      "latency_ms": 5, **message_out(assistant_msg)},
        })

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

    user_msg = ChatMessage(thread_id=thread.id, role="user", content=masked_message)
    db.add(user_msg)

    history = list((await db.execute(
        select(ChatMessage).where(ChatMessage.thread_id == thread.id)
        .order_by(ChatMessage.created_at).limit(30))).scalars().all())
    lc_messages: list[BaseMessage] = [
        HumanMessage(content=m.content) if m.role == "user" else AIMessage(content=m.content)
        for m in history
    ]
    lc_messages.append(HumanMessage(content=user_msg.content))
    return Turn(thread=thread, masked_message=masked_message, pii_count=pii_count, lc_messages=lc_messages)


async def complete_turn(db: AsyncSession, user: User, body: SendIn, turn: Turn, reply: AIMessage,
                        latency_ms: int, collector: dict | None) -> dict:
    """Persist the assistant reply (with blocks and pending actions) and its eval log."""
    provider = (reply.response_metadata or {}).get("provider") or (
        (getattr(reply, "response_metadata", {}) or {}).get("llm_output", {}) or {}
    ).get("provider") or "mock_openai"

    route_meta = (reply.response_metadata or {}).get("route")
    if route_meta and route_meta in ROUTE_NAMES:
        route_chosen = route_meta
    elif body.agent_mode and body.agent_mode != "auto":
        route_chosen = body.agent_mode
    else:
        route_chosen = route_of(body.agent_mode, body.message, page_context=body.page_context)

    extra = None
    if collector and (collector.get("blocks") or collector.get("actions")):
        extra = {"blocks": collector.get("blocks", []), "actions": collector.get("actions", [])}

    content = reply.content if isinstance(reply.content, str) else "".join(map(str, reply.content))
    assistant_msg = ChatMessage(thread_id=turn.thread.id, role="assistant", content=content,
                                provider=provider, latency_ms=latency_ms, tool_calls=extra)
    db.add(assistant_msg)
    await db.flush()

    is_jev = provider in jev.HANDLERS
    # LLM token counts remain the existing word-count estimate; JEV turns use no LLM at all.
    tokens_in = 0 if is_jev else max(1, len(turn.masked_message.split()) * 2)
    tokens_out = 0 if is_jev else max(1, len(content.split()) * 2)
    db.add(AiEvalLog(
        user_id=user.id, thread_id=turn.thread.id, message_id=assistant_msg.id,
        provider_used=provider, model_name="jev" if is_jev else settings.llm_primary_model,
        tokens_in=tokens_in, tokens_out=tokens_out,
        latency_ms=latency_ms, route_chosen=route_chosen,
        confidence_score=(reply.response_metadata or {}).get("jev_confidence", 0.95),
        pii_fields_masked=turn.pii_count, query_summary=turn.masked_message[:120],
    ))
    jev.record_request(provider, latency_ms, tokens_in + tokens_out)
    turn.thread.updated_at = utcnow()
    await db.flush()
    return {
        "thread_id": str(turn.thread.id),
        "reply": {"role": "assistant", "content": content, "provider": provider,
                  "latency_ms": latency_ms, **message_out(assistant_msg)},
    }


# ── Pending actions ─────────────────────────────────────────────────────

async def _owned_message(db: AsyncSession, user: User, message_id: uuid.UUID) -> tuple[ChatMessage, ChatThread]:
    row = (await db.execute(
        select(ChatMessage, ChatThread).join(ChatThread, ChatMessage.thread_id == ChatThread.id)
        .where(ChatMessage.id == message_id, ChatThread.user_id == user.id))).first()
    if not row:
        raise HTTPException(404, "Message not found")
    return row[0], row[1]


async def _apply(db: AsyncSession, user: User, action: dict) -> dict:
    """Execute a confirmed proposal through the same validation the REST endpoints use."""
    from app.schemas.planning import BudgetCreate, GoalCreate
    from app.services import txn_service

    kind, payload = action.get("type"), action.get("payload") or {}
    if kind == "create_goal":
        body = GoalCreate(**payload)
        goal = Goal(user_id=user.id, **body.model_dump())
        db.add(goal)
        await db.flush()
        return {"goal_id": str(goal.id)}

    if kind == "create_budget":
        body = BudgetCreate(**{**payload, "start_date": utcnow().date()})
        cat_ids = {e.category_id for e in body.envelopes}
        allowed = set((await db.execute(select(Category.id).where(
            Category.id.in_(cat_ids), (Category.user_id == user.id) | (Category.user_id.is_(None))))).scalars())
        if cat_ids - allowed:
            raise HTTPException(422, "Proposal references a category you cannot use")
        budget = Budget(user_id=user.id, name=body.name, strategy=body.strategy, start_date=body.start_date,
                        income_planned_minor=body.income_planned_minor, currency=body.currency.upper())
        db.add(budget)
        await db.flush()
        for e in body.envelopes:
            db.add(BudgetEnvelope(budget_id=budget.id, category_id=e.category_id, name=e.name,
                                  allocated_minor=e.allocated_minor, rollover=e.rollover))
        await db.flush()
        return {"budget_id": str(budget.id)}

    if kind == "recategorize":
        category_id = uuid.UUID(str(payload["category_id"]))
        cat = await db.scalar(select(Category).where(
            Category.id == category_id, (Category.user_id == user.id) | (Category.user_id.is_(None))))
        if not cat:
            raise HTTPException(422, "Proposal references a category you cannot use")
        updated = 0
        for raw_id in payload.get("transaction_ids", [])[:50]:
            txn_id = uuid.UUID(str(raw_id))
            owned = await db.scalar(select(Transaction.id).where(
                Transaction.id == txn_id, Transaction.user_id == user.id))
            if owned and await txn_service.confirm_category(db, user.id, txn_id, category_id):
                updated += 1
        await db.flush()
        return {"updated": updated}

    raise HTTPException(422, f"Unsupported action type: {kind}")


async def decide_action(db: AsyncSession, user: User, message_id: uuid.UUID, action_id: str,
                        decision: str) -> dict:
    """Confirm or cancel one pending proposal. Idempotent: a decided action cannot be re-applied."""
    msg, _thread = await _owned_message(db, user, message_id)
    extra = dict(msg.tool_calls or {})
    actions = [dict(a) for a in extra.get("actions", [])]
    action = next((a for a in actions if a.get("id") == action_id), None)
    if not action:
        raise HTTPException(404, "Action not found")
    if action.get("status") != "pending":
        raise HTTPException(409, f"Action already {action.get('status')}")

    if decision == "confirm":
        action["result"] = await _apply(db, user, action)
        action["status"] = "confirmed"
    else:
        action["status"] = "cancelled"
    action["decided_at"] = utcnow().isoformat()

    msg.tool_calls = {**extra, "actions": actions}
    flag_modified(msg, "tool_calls")
    await db.flush()
    return action


async def pending_actions(db: AsyncSession, user: User, limit: int = 50) -> list[dict]:
    rows = (await db.execute(
        select(ChatMessage, ChatThread).join(ChatThread, ChatMessage.thread_id == ChatThread.id)
        .where(ChatThread.user_id == user.id, ChatThread.archived.is_(False),
               ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_at.desc()).limit(300))).all()
    out: list[dict] = []
    for msg, thread in rows:
        for a in (msg.tool_calls or {}).get("actions", []):
            if a.get("status") == "pending":
                out.append({**a, "message_id": str(msg.id), "thread_id": str(thread.id),
                            "thread_title": thread.title, "source_tab": thread.source_tab,
                            "created_at": msg.created_at.isoformat() if msg.created_at else None})
    return out[:limit]
