from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import seal
from app.db.session import get_db
from app.models import BankConnection, User
from app.services.deps import get_current_user
from app.services.providers import (
    AggregationError,
    available_providers,
    get_providers,
    sync_connection,
)

router = APIRouter(prefix="/connections", tags=["integrations"])


@router.get("/providers")
async def list_providers():
    return {"providers": available_providers()}


class LinkStartIn(BaseModel):
    provider: str


@router.post("/link/start")
async def link_start(body: LinkStartIn, user: User = Depends(get_current_user)):
    providers = get_providers()
    p = providers.get(body.provider)
    if not p:
        raise HTTPException(404, "Unknown provider")
    if not p.is_configured():
        raise HTTPException(503, f"{body.provider} not configured on server — set its API keys in .env")
    result = await p.create_link(str(user.id), None)
    return result


@router.post("/link/complete")
async def link_complete(body: dict = Body(...), user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Exchange public token / requisition id / basiq user id → stored connection."""
    providers = get_providers()
    key = body.get("provider")
    p = providers.get(key)
    if not p:
        raise HTTPException(404, "Unknown provider")
    external_ref = body.get("public_token") or body.get("requisition_id") or body.get("basiq_user_id")
    if not external_ref:
        raise HTTPException(400, "Missing public_token / requisition_id / basiq_user_id")
    try:
        ext_id = await p.exchange(external_ref)
    except AggregationError as exc:
        raise HTTPException(400, str(exc))
    conn = BankConnection(user_id=user.id, provider=key, region=p.region,
                          external_id=ext_id, institution_name=body.get("institution_name"))
    if key == "plaid" and getattr(p, "last_access_token", None):
        conn.access_token_sealed = seal(p.last_access_token)
        p.last_access_token = None  # hygiene: don't retain in memory
    db.add(conn)
    await db.flush()
    return {"connection_id": str(conn.id), "provider": key}


@router.get("")
async def list_connections(user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(BankConnection).where(BankConnection.user_id == user.id))).scalars().all()
    return [{"id": str(c.id), "provider": c.provider, "region": c.region,
             "institution_name": c.institution_name, "status": c.status} for c in rows]


@router.post("/{connection_id}/sync")
async def sync(connection_id: uuid.UUID, user: User = Depends(get_current_user),
               db: AsyncSession = Depends(get_db)):
    conn = await db.get(BankConnection, connection_id)
    if not conn or conn.user_id != user.id:
        raise HTTPException(404, "Connection not found")
    p = get_providers().get(conn.provider)
    if not p or not p.is_configured():
        raise HTTPException(503, "Provider unavailable")
    try:
        return await sync_connection(db, user.id, conn, p)
    except AggregationError as exc:
        raise HTTPException(502, str(exc))


@router.delete("/{connection_id}", status_code=204)
async def revoke(connection_id: uuid.UUID, user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    conn = await db.get(BankConnection, connection_id)
    if conn and conn.user_id == user.id:
        conn.status = "revoked"
    return None
