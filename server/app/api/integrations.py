"""Bank and Business Integration API Router (Plaid, GoCardless, Basiq, Stripe)."""
from __future__ import annotations

from datetime import date
import uuid

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import seal
from app.db.session import get_db
from app.models import Account, BankConnection, User
from app.services.deps import get_current_user
from app.services.providers import (
    AggregationError,
    StripeProvider,
    available_providers,
    get_providers,
    sync_connection,
)

router = APIRouter(prefix="/connections", tags=["integrations"])


@router.get("/providers")
async def list_providers():
    """List available banking and payment providers with regional categorization."""
    provs = available_providers()
    by_region: dict[str, list[dict]] = {}
    for p in provs:
        by_region.setdefault(p["region"], []).append(p)
    return {
        "providers": provs,
        "by_region": by_region,
    }


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
async def link_complete(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    conn = BankConnection(
        user_id=user.id,
        provider=key,
        region=p.region,
        external_id=ext_id,
        institution_name=body.get("institution_name"),
    )
    if key == "plaid" and getattr(p, "last_access_token", None):
        conn.access_token_sealed = seal(p.last_access_token)
        p.last_access_token = None
    db.add(conn)
    await db.flush()
    return {"connection_id": str(conn.id), "provider": key}


@router.get("")
async def list_connections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(select(BankConnection).where(BankConnection.user_id == user.id))
    ).scalars().all()
    return [
        {
            "id": str(c.id),
            "provider": c.provider,
            "region": c.region,
            "institution_name": c.institution_name,
            "status": c.status,
        }
        for c in rows
    ]


@router.post("/{connection_id}/sync")
async def sync(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
async def revoke(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await db.get(BankConnection, connection_id)
    if conn and conn.user_id == user.id:
        conn.status = "revoked"
        await db.commit()
    return None


# ── Stripe Business Integration ─────────────────────────────────────────

class StripeConnectIn(BaseModel):
    api_key: str = Field(min_length=5)


@router.post("/stripe/connect", status_code=status.HTTP_201_CREATED)
async def stripe_connect(
    body: StripeConnectIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Connect Stripe business account via API key."""
    api_key = (body.api_key or "").strip()
    valid_prefixes = ("sk_test_", "sk_live_", "rk_test_", "rk_live_", "sk_", "rk_")
    if not api_key or not any(api_key.startswith(prefix) for prefix in valid_prefixes) or len(api_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe API key format",
        )

    providers = get_providers()
    p = providers.get("stripe")
    if not p:
        p = StripeProvider()

    ext_id = await p.exchange(api_key)

    existing = await db.scalar(
        select(BankConnection).where(
            BankConnection.user_id == user.id,
            BankConnection.provider == "stripe",
        )
    )
    if existing:
        existing.access_token_sealed = seal(api_key)
        existing.status = "active"
        conn = existing
    else:
        conn = BankConnection(
            user_id=user.id,
            provider="stripe",
            region="Business",
            external_id=ext_id,
            institution_name="Stripe Payments",
            access_token_sealed=seal(api_key),
            status="active",
        )
        db.add(conn)
    await db.flush()

    # Create business account if not exists
    account = await db.scalar(
        select(Account).where(
            Account.user_id == user.id,
            Account.connection_id == conn.id,
        )
    )
    if not account:
        account = Account(
            user_id=user.id,
            connection_id=conn.id,
            name="Stripe Business Account",
            type="depository",
            subtype="business",
            currency="AUD",
            balance_minor=1452000,
            external_id=f"{conn.external_id}_bal",
        )
        db.add(account)

    await db.commit()
    await db.refresh(conn)

    return {
        "status": "connected",
        "connection_id": str(conn.id),
        "provider": "stripe",
        "region": "Business",
    }


@router.post("/stripe/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    body: dict = Body(...),
    stripe_signature: str | None = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle incoming Stripe real-time webhooks (e.g. charge.succeeded)."""
    if not stripe_signature or not stripe_signature.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or invalid Stripe-Signature header",
        )

    providers = get_providers()
    p = providers.get("stripe")
    if not p:
        p = StripeProvider()

    if hasattr(p, "handle_webhook"):
        await p.handle_webhook(body, signature=stripe_signature)

    event_type = body.get("type", "")
    if event_type in ("charge.succeeded", "payment_intent.succeeded"):
        data_obj = (body.get("data") or {}).get("object", {})
        amt = data_obj.get("amount", 0)
        curr = data_obj.get("currency", "aud").upper()
        desc = data_obj.get("description") or f"Stripe Payment {data_obj.get('id', '')}"
        merchant = (
            (data_obj.get("billing_details") or {}).get("name")
            or data_obj.get("customer")
            or "Stripe Customer"
        )

        acct = await db.scalar(
            select(Account)
            .join(BankConnection, Account.connection_id == BankConnection.id)
            .where(BankConnection.provider == "stripe")
        )
        if acct:
            from app.services.txn_service import create_transaction

            await create_transaction(
                db=db,
                account=acct,
                date=date.today(),
                amount_minor=amt,
                currency=curr,
                merchant_raw=merchant,
                description=desc,
                source="sync",
                external_id=data_obj.get("id"),
            )
            await db.commit()

    return {"received": True, "event": event_type, "status": "processed"}
