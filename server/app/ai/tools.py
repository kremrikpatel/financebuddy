"""Agent tools — scoped, read-mostly data access for the AI engine.

Every tool receives the request context (user_id + db session) via a
contextvar set by the graph entry; tools never see raw credentials.
"""
from __future__ import annotations

import contextvars
import uuid
from datetime import date, timedelta

from langchain_core.tools import tool
from sqlalchemy import func, select

from app.ai.pii import mask_pii
from app.models import Account, Alert, Budget, BudgetEnvelope, Category, Debt, Goal, Transaction

_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar("agent_ctx", default={})


def set_agent_context(db, user_id: uuid.UUID) -> None:
    _ctx.set({"db": db, "user_id": user_id})


def agent_context() -> dict:
    return _ctx.get()


async def get_db_session():
    return agent_context()["db"]


def uid() -> uuid.UUID:
    return agent_context()["user_id"]


# ── Data tools ──────────────────────────────────────────────────────────

@tool
async def list_accounts() -> str:
    """List the user's accounts with balances and currencies."""
    db = await get_db_session()
    rows = (await db.execute(
        select(Account).where(Account.user_id == uid(), Account.archived.is_(False)))).scalars().all()
    lines = [f"- {a.name} ({a.type}, {a.currency}): {a.balance_minor/100:.2f}" for a in rows]
    total_by_ccy: dict[str, int] = {}
    for a in rows:
        total_by_ccy[a.currency] = total_by_ccy.get(a.currency, 0) + a.balance_minor
    totals = ", ".join(f"{v/100:.2f} {k}" for k, v in total_by_ccy.items())
    return f"Accounts:\n" + "\n".join(lines) + f"\nTotals: {totals or 'none'}"


@tool
async def search_transactions(query: str = "", category: str = "", days: int = 90,
                              limit: int = 20) -> str:
    """Search recent transactions by merchant/description text and optional
    category name. Returns masked summaries."""
    db = await get_db_session()
    since = date.today() - timedelta(days=min(days, 365))
    q = select(Transaction).where(
        Transaction.user_id == uid(), Transaction.date >= since).order_by(
        Transaction.date.desc()).limit(min(limit, 50))
    if query:
        q = q.where(Transaction.merchant_norm.ilike(f"%{query.lower()}%"))
    if category:
        cat = await db.scalar(select(Category).where(
            Category.name.ilike(category), 
            (Category.user_id == uid()) | (Category.user_id.is_(None))))
        if cat:
            q = q.where(Transaction.category_id == cat.id)
        else:
            return f"No category named '{category}' found."
    rows = (await db.execute(q)).scalars().all()
    out = []
    for t in rows:
        desc = mask_pii(t.description) if t.description else ""
        out.append(f"{t.date.isoformat()} {t.merchant_raw[:40]} "
                   f"{t.amount_minor/100:+.2f} {t.currency}"
                   + (f" ({desc[:60]})" if desc else ""))
    return "\n".join(out) or "No matching transactions."


@tool
async def spending_summary(days: int = 30) -> str:
    """Aggregate spend by category for the last N days."""
    db = await get_db_session()
    since = date.today() - timedelta(days=min(days, 365))
    q = (
        select(Category.name, func.sum(func.abs(Transaction.amount_minor)))
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.user_id == uid(), Transaction.is_income.is_(False),
               Transaction.excluded.is_(False), Transaction.date >= since)
        .group_by(Category.name).order_by(func.sum(func.abs(Transaction.amount_minor)).desc())
    )
    rows = (await db.execute(q)).all()
    total = sum(r[1] or 0 for r in rows)
    lines = [f"- {name}: {(amt or 0)/100:.2f}" for name, amt in rows[:15]]
    return f"Spend last {days}d — total {total/100:.2f}:\n" + "\n".join(lines)


@tool
async def budget_status() -> str:
    """Current month's envelope budgets: allocated vs spent vs remaining."""
    db = await get_db_session()
    from app.services.budget_engine import envelope_status

    budget = await db.scalar(select(Budget).where(
        Budget.user_id == uid(), Budget.active.is_(True)).order_by(Budget.start_date.desc()))
    if not budget:
        return "No active budget."
    today = date.today()
    statuses = await envelope_status(db, budget, today.year, today.month)
    lines = [f"- {s.name}: allocated {s.allocated_minor/100:.2f}, spent {s.spent_minor/100:.2f}, "
             f"{'OVER by ' + format(abs(s.remaining_minor)/100, '.2f') if s.overspent else 'remaining ' + format(s.remaining_minor/100, '.2f')} ({s.pct_used}%)"
             for s in statuses]
    return f"Budget '{budget.name}' ({budget.strategy}):\n" + "\n".join(lines)


@tool
async def forecast_cashflow(months: int = 6) -> str:
    """Project net cash flow using Holt trend forecasting over monthly history."""
    db = await get_db_session()
    from app.services.forecaster import forecast_net_flow, runway_months
    from app.services.txn_service import monthly_flows

    flows = await monthly_flows(db, uid())
    if len(flows) < 3:
        return "Need at least 3 months of history to forecast."
    nets = [f["income_minor"] - f["expense_minor"] for f in flows]
    fc = forecast_net_flow(nets, horizon=min(max(months, 1), 12))
    accounts = (await db.execute(select(Account).where(Account.user_id == uid()))).scalars().all()
    balance = sum(a.balance_minor for a in accounts if a.type != "credit")
    runway = runway_months(balance, fc["forecast"])
    trend = "rising" if fc["trend_per_month"] > 0 else ("falling" if fc["trend_per_month"] < 0 else "stable")
    msg = (f"Net-flow trend is {trend} ({fc['trend_per_month']/100:+.2f}/mo).\n"
           f"Projected next months: {[round(v/100) for v in fc['forecast']]}\n"
           f"Current liquid balance ≈ {balance/100:.2f}.")
    if runway is not None:
        msg += f"\n⚠️ Runway: ~{runway} months before balance depletion."
    return msg


@tool
async def goal_overview() -> str:
    """All savings goals with progress and on-track status."""
    db = await get_db_session()
    rows = (await db.execute(select(Goal).where(Goal.user_id == uid()))).scalars().all()
    if not rows:
        return "No goals yet."
    out = []
    for g in rows:
        pct = min(100, g.saved_minor / g.target_minor * 100 if g.target_minor else 0)
        eta = ""
        if g.target_date:
            eta = f", target {g.target_date.isoformat()}"
        out.append(f"- {g.name}: {pct:.0f}% ({g.saved_minor/100:.2f}/{g.target_minor/100:.2f} {g.currency}{eta})")
    return "\n".join(out)


@tool
async def debt_overview() -> str:
    """All tracked debts with APRs, minimum payments, and payoff comparison."""
    db = await get_db_session()
    rows = (await db.execute(select(Debt).where(Debt.user_id == uid()))).scalars().all()
    if not rows:
        return "No debts tracked."
    from app.services.goals_debt import compare_strategies

    payload = [{"name": d.name, "principal_minor": d.principal_minor,
                "apr_bps": d.apr_bps, "min_payment_minor": d.min_payment_minor} for d in rows]
    cmp = compare_strategies(payload)
    lines = [f"- {d.name}: {d.principal_minor/100:.2f} @ {d.apr_bps/100:.2f}% APR "
             f"(min {d.min_payment_minor/100:.2f})" for d in rows]
    return ("\n".join(lines)
            + f"\n\nAvalanche: {cmp['avalanche']['months']}mo, interest {cmp['avalanche']['total_interest_minor']/100:.2f}"
            + f"\nSnowball: {cmp['snowball']['months']}mo, interest {cmp['snowball']['total_interest_minor']/100:.2f}"
            + f"\nAvalanche saves {cmp['interest_saved_by_avalanche_minor']/100:.2f} in interest")


@tool
async def recent_alerts(limit: int = 10) -> str:
    """Latest fraud/anomaly/budget alerts."""
    db = await get_db_session()
    rows = (await db.execute(
        select(Alert).where(Alert.user_id == uid()).order_by(Alert.created_at.desc())
        .limit(min(limit, 25)))).scalars().all()
    if not rows:
        return "No alerts."
    return "\n".join(f"- [{a.severity.upper()}] {a.title}: {(a.body or '')[:120]}" for a in rows)


@tool
async def subscriptions_detected() -> str:
    """Detected recurring subscriptions and their monthly cost estimate."""
    db = await get_db_session()
    from app.services.subscriptions import detect_subscriptions

    txns = (await db.execute(
        select(Transaction).where(Transaction.user_id == uid(),
                                  Transaction.is_income.is_(False))
        .order_by(Transaction.date.desc()).limit(600))).scalars().all()
    detected = detect_subscriptions([
        {"merchant_norm": t.merchant_norm, "amount_minor": t.amount_minor,
         "currency": t.currency, "date": t.date,
         "display_name": t.merchant_raw} for t in txns])
    if not detected:
        return "No recurring subscriptions detected."
    monthly_total = sum(s.avg_amount_minor * (30 / s.cadence_days) for s in detected)
    lines = [f"- {s.display_name}: {s.avg_amount_minor/100:.2f} {s.currency} every {s.cadence_days}d "
             f"(next ~{s.next_expected.isoformat() if s.next_expected else '?'})" for s in detected[:15]]
    return "\n".join(lines) + f"\nEstimated monthly subscription spend: {monthly_total/100:.2f}"


ALL_TOOLS = [
    list_accounts, search_transactions, spending_summary, budget_status,
    forecast_cashflow, goal_overview, debt_overview, recent_alerts,
    subscriptions_detected,
]


# ── Write tools (explicit user-intent only) ─────────────────────────────

@tool
async def create_goal_draft(name: str, target_amount: float, currency: str,
                            monthly_amount: float, target_date_iso: str | None = None) -> str:
    """Create a savings goal draft. Amounts in major units."""
    db = await get_db_session()
    target_date = date.fromisoformat(target_date_iso) if target_date_iso else None
    goal = Goal(user_id=uid(), name=name, target_minor=round(target_amount * 100),
                currency=currency.upper(), monthly_amount_minor=round(monthly_amount * 100),
                target_date=target_date, strategy="fixed_monthly")
    db.add(goal)
    await db.flush()
    return f"Goal '{name}' created: {target_amount:.2f} {currency}, {monthly_amount:.2f}/month."


WRITE_TOOLS = [create_goal_draft]

AGENT_TOOLS = ALL_TOOLS + WRITE_TOOLS
