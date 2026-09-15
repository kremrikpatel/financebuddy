"""AI Observability and Evaluation API Router."""
from __future__ import annotations

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.ai import AiEvalLog
from app.models.user import User
from app.services.deps import get_current_user

router = APIRouter(prefix="/ai", tags=["ai_eval"])


class AiEvalLogOut(BaseModel):
    id: str
    user_id: str
    thread_id: str | None
    message_id: str | None
    provider_used: str
    model_name: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    route_chosen: str
    confidence_score: float
    pii_fields_masked: int
    query_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AiEvalHistoryResponse(BaseModel):
    items: list[AiEvalLogOut]
    total: int
    page: int
    limit: int


@router.get("/eval/history", response_model=AiEvalHistoryResponse)
async def get_eval_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return paginated AI evaluation logs and telemetry metrics for the current user."""
    offset = (page - 1) * limit

    # Count total
    count_stmt = select(func.count(AiEvalLog.id)).where(AiEvalLog.user_id == user.id)
    total = (await db.scalar(count_stmt)) or 0

    # Query items
    items_stmt = (
        select(AiEvalLog)
        .where(AiEvalLog.user_id == user.id)
        .order_by(AiEvalLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(items_stmt)).scalars().all()

    items = [
        AiEvalLogOut(
            id=str(r.id),
            user_id=str(r.user_id),
            thread_id=str(r.thread_id) if r.thread_id else None,
            message_id=str(r.message_id) if r.message_id else None,
            provider_used=r.provider_used,
            model_name=r.model_name,
            tokens_in=r.tokens_in or 0,
            tokens_out=r.tokens_out or 0,
            latency_ms=r.latency_ms or 0,
            route_chosen=r.route_chosen or "coach",
            confidence_score=r.confidence_score or 1.0,
            pii_fields_masked=r.pii_fields_masked or 0,
            query_summary=r.query_summary,
            created_at=r.created_at,
        )
        for r in rows
    ]

    return AiEvalHistoryResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
    )
