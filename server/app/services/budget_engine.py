"""Dynamic envelope & zero-based budgeting engine.

- Envelope status per month (allocated, spent, remaining, rollover carry).
- Zero-based validation: every planned dollar must be assigned.
- Suggested allocations from trailing 3-month category averages.
"""
from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Budget, BudgetEnvelope, Category, Transaction


@dataclass
class EnvelopeStatus:
    envelope_id: str | None
    name: str
    allocated_minor: int
    carry_in_minor: int
    spent_minor: int
    remaining_minor: int
    pct_used: float
    overspent: bool


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


async def envelope_status(db: AsyncSession, budget: Budget, year: int, month: int) -> list[EnvelopeStatus]:
    start, end = month_bounds(year, month)
    envelopes = (await db.execute(
        select(BudgetEnvelope).where(BudgetEnvelope.budget_id == budget.id))).scalars().all()
    cat_ids = [e.category_id for e in envelopes if e.category_id]
    cats = {c.id: c for c in (await db.execute(
        select(Category).where(Category.id.in_(cat_ids)))).scalars().all()} if cat_ids else {}

    spend_q = (
        select(Transaction.category_id, func.sum(Transaction.amount_minor))
        .where(
            Transaction.user_id == budget.user_id,
            Transaction.excluded.is_(False),
            Transaction.is_income.is_(False),
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .group_by(Transaction.category_id)
    )
    spent_by_cat = {cid: -total for cid, total in (await db.execute(spend_q)).all()}

    out: list[EnvelopeStatus] = []
    for e in envelopes:
        spent = abs(spent_by_cat.get(e.category_id, 0))
        remaining = e.allocated_minor + e.carry_in_minor - spent
        denom = e.allocated_minor + e.carry_in_minor
        out.append(EnvelopeStatus(
            envelope_id=str(e.id), name=e.name or (cats[e.category_id].name if e.category_id and e.category_id in cats else "General"),
            allocated_minor=e.allocated_minor, carry_in_minor=e.carry_in_minor,
            spent_minor=spent, remaining_minor=remaining,
            pct_used=round(spent / denom * 100, 1) if denom > 0 else 0.0,
            overspent=remaining < 0,
        ))
    return out


def zero_based_check(envelopes: list[dict], income_planned_minor: int) -> dict:
    """Every unit of income must have a job."""
    allocated = sum(e["allocated_minor"] for e in envelopes)
    unassigned = income_planned_minor - allocated
    return {
        "income_planned_minor": income_planned_minor,
        "assigned_minor": allocated,
        "unassigned_minor": unassigned,
        "balanced": unassigned == 0,
        "message": ("Fully balanced — every dollar has a job."
                    if unassigned == 0 else
                    f"{unassigned / 100:.2f} left to assign" if unassigned > 0 else
                    f"Over-assigned by {abs(unassigned) / 100:.2f}"),
    }


async def suggest_allocations(db: AsyncSession, user_id: uuid.UUID,
                              currency: str = "USD") -> list[dict]:
    """Trailing 3-month averages per category → suggested monthly envelopes."""
    today = date.today()
    first_of_month = today.replace(day=1)
    start = (first_of_month - timedelta(days=93)).replace(day=1)
    q = (
        select(Transaction.category_id, func.avg(func.abs(Transaction.amount_minor)))
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == user_id,
            Transaction.is_income.is_(False),
            Transaction.excluded.is_(False),
            Transaction.date >= start,
            Category.kind == "expense",
        )
        .group_by(Transaction.category_id)
    )
    rows = (await db.execute(q)).all()
    out = []
    for cid, avg_abs in rows:
        out.append({"category_id": str(cid), "suggested_monthly_minor": round(float(avg_abs or 0))})
    return sorted(out, key=lambda r: -r["suggested_monthly_minor"])


def check_threshold(statuses: list[EnvelopeStatus]) -> list[str]:
    """Envelope ids crossing warn (80%) or overspend thresholds."""
    warnings = []
    for s in statuses:
        if s.envelope_id:
            if s.overspent or s.pct_used >= 80:
                warnings.append(s.envelope_id)
    return warnings
