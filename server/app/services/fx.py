"""FX rates: daily cache in Postgres, open.er-api.com source, static fallback."""
from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models import FxRate
from app.db.base import utcnow

log = get_logger("fx")

# Comprehensive offline fallback across 150+ ISO-4217 world currencies relative to 1 USD
_FALLBACK_USD: dict[str, float] = {
    "USD": 1.0, "EUR": 0.92, "GBP": 0.79, "AUD": 1.52, "CAD": 1.36,
    "INR": 83.2, "JPY": 150.5, "SGD": 1.34, "CHF": 0.88, "NZD": 1.64,
    "AED": 3.67, "AFN": 71.5, "ALL": 94.2, "AMD": 387.0, "ANG": 1.79,
    "AOA": 835.0, "ARS": 870.0, "AWG": 1.79, "AZN": 1.70, "BAM": 1.80,
    "BBD": 2.0, "BDT": 110.0, "BGN": 1.80, "BHD": 0.376, "BIF": 2860.0,
    "BMD": 1.0, "BND": 1.34, "BOB": 6.91, "BRL": 5.05, "BSD": 1.0,
    "BTN": 83.2, "BWP": 13.6, "BYN": 3.27, "BZD": 2.0, "CDF": 2750.0,
    "CLP": 945.0, "CNY": 7.24, "COP": 3900.0, "CRC": 515.0, "CUP": 24.0,
    "CVE": 101.5, "CZK": 23.4, "DJF": 177.7, "DKK": 6.87, "DOP": 58.5,
    "DZD": 134.5, "EGP": 47.8, "ERN": 15.0, "ETB": 57.0, "FJD": 2.25,
    "FKP": 0.79, "GEL": 2.68, "GGP": 0.79, "GHS": 13.5, "GIP": 0.79,
    "GMD": 67.5, "GNF": 8600.0, "GTQ": 7.80, "GYD": 209.0, "HKD": 7.82,
    "HNL": 24.7, "HRK": 6.93, "HTG": 132.5, "HUF": 360.0, "IDR": 15800.0,
    "ILS": 3.72, "IMP": 0.79, "IQD": 1310.0, "IRR": 42000.0, "ISK": 139.0,
    "JEP": 0.79, "JMD": 155.0, "JOD": 0.709, "KES": 132.0, "KGS": 89.0,
    "KHR": 4080.0, "KMF": 452.0, "KPW": 900.0, "KRW": 1340.0, "KWD": 0.307,
    "KYD": 0.83, "KZT": 450.0, "LAK": 21000.0, "LBP": 89500.0, "LKR": 300.0,
    "LRD": 192.0, "LSL": 18.5, "LYD": 4.85, "MAD": 10.1, "MDL": 17.7,
    "MGA": 4450.0, "MKD": 56.7, "MMK": 2100.0, "MNT": 3450.0, "MOP": 8.05,
    "MRU": 39.5, "MUR": 46.0, "MVR": 15.4, "MWK": 1730.0, "MXN": 16.7,
    "MYR": 4.75, "MZN": 63.8, "NAD": 18.5, "NGN": 1300.0, "NIO": 36.8,
    "NOK": 10.8, "NPR": 133.0, "NZD": 1.66, "OMR": 0.384, "PAB": 1.0,
    "PEN": 3.70, "PGK": 3.80, "PHP": 57.0, "PKR": 278.0, "PLN": 3.98,
    "PYG": 7400.0, "QAR": 3.64, "RON": 4.58, "RSD": 108.0, "RUB": 92.5,
    "RWF": 1290.0, "SAR": 3.75, "SBD": 8.45, "SCR": 13.5, "SDG": 600.0,
    "SEK": 10.8, "SHP": 0.79, "SLL": 22500.0, "SOS": 571.0, "SRD": 35.0,
    "SSP": 130.0, "STN": 22.5, "SYP": 13000.0, "SZL": 18.5, "THB": 36.5,
    "TJS": 10.9, "TMT": 3.50, "TND": 3.12, "TOP": 2.35, "TRY": 32.2,
    "TTD": 6.78, "TWD": 32.2, "TZS": 2580.0, "UAH": 39.5, "UGX": 3800.0,
    "UYU": 38.8, "UZS": 12600.0, "VES": 36.3, "VND": 25000.0, "VUV": 120.0,
    "WST": 2.75, "XAF": 603.5, "XCD": 2.70, "XOF": 603.5, "XPF": 110.0,
    "YER": 250.0, "ZAR": 18.5, "ZMW": 25.5, "ZWL": 13.5,
}

_CACHE_TTL_SECONDS = 12 * 3600


async def get_rate(db: AsyncSession, base: str, quote: str) -> float:
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return 1.0
    
    # 1. Check DB Cache
    row = await _get_fx_row(db, base, quote)
    if row and (utcnow() - row.updated_at).total_seconds() < _CACHE_TTL_SECONDS:
        return row.rate
    
    # 2. Live API fetch
    rate = await _fetch_rate(base, quote)
    if rate is not None:
        await _upsert(db, base, quote, rate)
        await _upsert(db, quote, base, 1.0 / rate)
        return rate
    
    # 3. Try inverse stored in DB
    inv = await _get_fx_row(db, quote, base)
    if inv and inv.rate:
        return 1.0 / inv.rate
    
    # 4. USD Triangulation in DB
    usd_b = await _get_fx_row(db, "USD", base)
    usd_q = await _get_fx_row(db, "USD", quote)
    if usd_b and usd_q and usd_b.rate:
        return usd_q.rate / usd_b.rate
    
    # 5. Offline Fallback Table
    fb = _FALLBACK_USD.get(base)
    fq = _FALLBACK_USD.get(quote)
    if fb and fq:
        return fq / fb
    elif fb and quote == "USD":
        return 1.0 / fb
    elif base == "USD" and fq:
        return fq
    
    raise ValueError(f"No FX rate available for {base}->{quote}")


async def _get_fx_row(db: AsyncSession, base: str, quote: str) -> FxRate | None:
    try:
        return await db.scalar(
            select(FxRate).where(FxRate.base == base, FxRate.quote == quote)
        )
    except Exception:
        return None


async def _fetch_rate(base: str, quote: str) -> float | None:
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.get(f"{settings.fx_api_base}/{base}")
            r.raise_for_status()
            data = r.json()
            q = data.get("rates", {}).get(quote)
            return float(q) if q else None
    except Exception as exc:  # network down / bad key — degrade quietly
        log.warning("fx_fetch_failed", base=base, quote=quote, error=str(exc))
        return None


async def _upsert(db: AsyncSession, base: str, quote: str, rate: float) -> None:
    try:
        row = await _get_fx_row(db, base, quote)
        if row:
            row.rate = rate
        else:
            db.add(FxRate(base=base, quote=quote, rate=rate))
    except Exception:
        pass


async def convert_minor(db: AsyncSession, amount_minor: int, src: str, dst: str) -> int:
    rate = await get_rate(db, src, dst)
    return round(amount_minor * rate)
