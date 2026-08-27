from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_router import active_providers
from app.core.config import settings
from app.db.session import get_db
from app.services.deps import get_current_user

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    checks = {"api": "ok"}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {str(exc)[:100]}"
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        checks["redis"] = "ok"
        await r.aclose()
    except Exception as exc:
        checks["redis"] = f"unavailable: {str(exc)[:80]}"
    return {"status": "degraded" if any(v != "ok" for v in checks.values()) else "ok",
            **checks, "llm_providers": active_providers()}


@router.get("/currencies/rates")
async def fx_rates(base: str = "USD", quote: str = "EUR",
                   user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.fx import get_rate

    try:
        rate = await get_rate(db, base, quote)
        return {"base": base.upper(), "quote": quote.upper(), "rate": round(rate, 6)}
    except ValueError as exc:
        return {"error": str(exc)}


@router.get("/i18n/{lang}")
async def i18n_catalog(lang: str):
    """Server-side strings for alerts/emails (UI catalogs ship with the client)."""
    from app.i18n.catalogs import CATALOGS

    return {"lang": lang, "strings": CATALOGS.get(lang, CATALOGS["en"])}
