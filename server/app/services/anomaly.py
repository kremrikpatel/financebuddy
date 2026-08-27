"""Anomaly & fraud detection service.

Runs on transaction.created events:
- statistical spike detection (EWMA baseline + z-score per category)
- duplicate charge detection
- velocity check (burst of charges in 24h)
- subscription duplicates surfaced as alerts
Creates Alert rows and emits alert.created events.
"""
from __future__ import annotations

import uuid
from datetime import date

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, Transaction
from app.services.events import bus, new_event
from app.services.subscriptions import detect_duplicate_charges


async def recent_user_txns(db: AsyncSession, user_id: uuid.UUID, limit: int = 500) -> list[Transaction]:
    return list((await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id, Transaction.excluded.is_(False))
        .order_by(Transaction.date.desc())
        .limit(limit)
    )).scalars().all())


def zscore_spike(amounts: list[float], candidate: float, window: int = 60,
                 min_history: int = 8) -> float | None:
    """z-score of candidate vs trailing baseline. None when insufficient history."""
    if len(amounts) < min_history:
        return None
    base = np.asarray(amounts[-window:], dtype=np.float64)
    mu, sd = float(base.mean()), float(base.std())
    if sd < 1e-9:
        if abs(candidate - mu) < 1e-9:
            return 0.0
        return 5.0 if candidate > mu else None
    return (candidate - mu) / sd


def ewma_spike(amounts: list[float], candidate: float, alpha: float = 0.25,
               min_history: int = 5) -> float | None:
    """EWMA (Exponentially Weighted Moving Average) anomaly scoring.
    Gives higher weight to recent transactions.
    """
    if len(amounts) < min_history:
        return None
    
    ewma_mean = float(amounts[0])
    ewma_var = 0.0
    for x in amounts[1:]:
        delta = float(x) - ewma_mean
        ewma_mean = ewma_mean + alpha * delta
        ewma_var = (1 - alpha) * (ewma_var + alpha * delta * delta)
    
    ewma_std = float(np.sqrt(ewma_var)) if ewma_var > 0 else (float(np.std(amounts)) or 1e-9)
    if ewma_std < 1e-9:
        if abs(candidate - ewma_mean) < 1e-9:
            return 0.0
        return 5.0 if candidate > ewma_mean else None
    return (candidate - ewma_mean) / ewma_std


def velocity_burst(txns: list[Transaction]) -> bool:
    """≥6 expenses in a rolling 24h window ending at the newest txn."""
    expenses = sorted([t for t in txns if t.amount_minor < 0], key=lambda t: t.date)
    if len(expenses) < 6:
        return False
    from datetime import timedelta

    last = expenses[-1].date
    window = [t for t in expenses if last - t.date <= timedelta(days=1)]
    return len(window) >= 6


async def analyze_transaction(db: AsyncSession, txn: Transaction,
                              history: list[Transaction] | None = None) -> list[Alert]:
    """Full anomaly pipeline for one new transaction. Returns created alerts."""
    alerts: list[Alert] = []
    history = history or await recent_user_txns(db, txn.user_id)
    others = [t for t in history if t.id != txn.id]

    # 1. Amount spike vs merchant / category baseline (EWMA + z-score)
    same_merchant = [abs(float(t.amount_minor)) for t in others
                     if t.merchant_norm == txn.merchant_norm]
    z_merch = zscore_spike(same_merchant[-30:], abs(float(txn.amount_minor)))
    ewma_merch = ewma_spike(same_merchant[-30:], abs(float(txn.amount_minor)))
    
    effective_spike = max(filter(lambda v: v is not None, [z_merch, ewma_merch]), default=None)
    if effective_spike is not None and effective_spike >= 3.0:
        alerts.append(Alert(
            user_id=txn.user_id, type="unusual_charge", severity="warning",
            title=f"Unusual charge at {txn.merchant_raw[:60]}",
            body=(f"{abs(txn.amount_minor)/100:.2f} {txn.currency} is {effective_spike:.1f}σ above your "
                  f"typical spend at this merchant."),
            payload={"transaction_id": str(txn.id), "z": round(effective_spike, 2)},
        ))

    # 2. Duplicate charge
    dup_candidates = detect_duplicate_charges(
        [{"id": t.id, "date": t.date, "amount_minor": t.amount_minor,
          "currency": t.currency, "merchant_norm": t.merchant_norm} for t in history])
    for d in dup_candidates:
        if d["suspect"]["id"] == str(txn.id):
            alerts.append(Alert(
                user_id=txn.user_id, type="duplicate_charge", severity="critical",
                title="Possible duplicate charge detected",
                body=f"{d['merchant']} charged the same amount twice within {d['gap_days']} day(s).",
                payload=d,
            ))

    # 3. Velocity burst
    if velocity_burst(history):
        already = any(a.type == "velocity_burst" for a in alerts)
        if not already:
            alerts.append(Alert(
                user_id=txn.user_id, type="velocity_burst", severity="warning",
                title="Rapid spending burst",
                body="6+ charges within 24 hours — review recent transactions.",
                payload={"transaction_id": str(txn.id)},
            ))

    for a in alerts:
        db.add(a)
    await db.flush()
    for a in alerts:
        await bus.publish(new_event("alert.created", str(txn.user_id),
                                    {"alert_id": str(a.id), "type": a.type,
                                     "severity": a.severity}))
    return alerts


async def scan_subscription_duplicates(db: AsyncSession, user_id: uuid.UUID,
                                       subs_payload: list[dict]) -> list[Alert]:
    from app.services.subscriptions import find_duplicate_subscriptions

    pairs = find_duplicate_subscriptions(subs_payload)
    alerts: list[Alert] = []
    for i, j in pairs:
        a, b = subs_payload[i], subs_payload[j]
        alerts.append(Alert(
            user_id=user_id, type="duplicate_subscription", severity="info",
            title=f"Possible duplicate subscriptions: {a.get('display_name', '')} / {b.get('display_name', '')}",
            body="Two similar recurring charges with matching cadence were found. "
                 "One may be redundant or an old trial still billing.",
            payload={"subscriptions": [a, b]},
        ))
    for a in alerts:
        db.add(a)
    if alerts:
        await db.flush()
        for a in alerts:
            await bus.publish(new_event("alert.created", str(user_id),
                                        {"alert_id": str(a.id), "type": a.type}))
    return alerts


async def overspend_check(db: AsyncSession, budget_id: uuid.UUID) -> None:
    """Called by event consumer after transaction.created."""
    from app.models import Budget
    from app.services.budget_engine import envelope_status, month_bounds

    budget = await db.get(Budget, budget_id)
    if not budget:
        return
    today = date.today()
    start, end = month_bounds(today.year, today.month)
    statuses = await envelope_status(db, budget, today.year, today.month)
    for s in statuses:
        if s.overspent:
            alert = Alert(
                user_id=budget.user_id, type="overspend", severity="warning",
                title=f"Over budget: {s.name}",
                body=f"You've spent {(abs(s.remaining_minor))/100:.2f} {budget.currency} "
                     f"beyond the {s.name} envelope.",
                payload={"envelope_id": s.envelope_id},
            )
            db.add(alert)
            await bus.publish(new_event("alert.created", str(budget.user_id),
                                        {"type": "overspend", "envelope": s.name}))
