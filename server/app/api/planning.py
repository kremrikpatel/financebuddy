from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Alert, Budget, BudgetEnvelope, Debt, Goal, Transaction, User
from app.schemas.planning import (
    AlertOut,
    BudgetCreate,
    BudgetOut,
    DebtCreate,
    DebtPayoffPlan,
    GoalContributionIn,
    GoalCreate,
    GoalOut,
)
from app.services.deps import get_current_user

router = APIRouter(tags=["planning"])


# ── Budgets ─────────────────────────────────────────────────────────────

@router.get("/budgets", response_model=list[BudgetOut])
async def list_budgets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Budget).where(Budget.user_id == user.id).order_by(Budget.start_date.desc()))).scalars().all()
    return rows


@router.post("/budgets", response_model=BudgetOut, status_code=201)
async def create_budget(body: BudgetCreate, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    budget = Budget(user_id=user.id, name=body.name, strategy=body.strategy,
                    start_date=body.start_date, income_planned_minor=body.income_planned_minor,
                    currency=body.currency.upper())
    db.add(budget)
    await db.flush()
    for e in body.envelopes:
        db.add(BudgetEnvelope(budget_id=budget.id, category_id=e.category_id,
                              name=e.name, allocated_minor=e.allocated_minor,
                              rollover=e.rollover))
    await db.flush()
    return budget


class BudgetStatusOut(BaseModel):
    month: str
    strategy: str
    envelopes: list[dict]
    zero_based: dict | None = None


@router.get("/budgets/{budget_id}/status/{year}/{month}", response_model=BudgetStatusOut)
async def budget_status(budget_id: uuid.UUID, year: int, month: int,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    from dataclasses import asdict

    from app.services.budget_engine import envelope_status, zero_based_check

    budget = await db.get(Budget, budget_id)
    if not budget or budget.user_id != user.id:
        raise HTTPException(404, "Budget not found")
    statuses = await envelope_status(db, budget, year, month)
    zb = (zero_based_check([{"allocated_minor": s.allocated_minor} for s in statuses],
                           budget.income_planned_minor)
          if budget.strategy == "zero_based" else None)
    return BudgetStatusOut(month=f"{year}-{month:02d}", strategy=budget.strategy,
                           envelopes=[asdict(s) for s in statuses], zero_based=zb)


@router.get("/budgets/suggestions")
async def allocation_suggestions(user: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    from app.services.budget_engine import suggest_allocations

    return {"suggestions": await suggest_allocations(db, user.id)}


# ── Goals ───────────────────────────────────────────────────────────────

@router.get("/goals", response_model=list[GoalOut])
async def list_goals(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Goal).where(Goal.user_id == user.id))).scalars().all()
    out = []
    avg_income = await _avg_monthly_income(db, user.id)
    from app.services.goals_debt import goal_on_track

    for g in rows:
        track = goal_on_track(g.strategy, g.saved_minor, g.target_minor,
                              g.monthly_amount_minor, g.percent_of_income,
                              avg_income, g.target_date)
        out.append({**GoalOut.model_validate(g).model_dump(), **track})
    return out


async def _avg_monthly_income(db: AsyncSession, user_id: uuid.UUID) -> int:
    from datetime import timedelta

    since = date.today() - timedelta(days=90)
    total = (await db.execute(
        select(Transaction.amount_minor).where(
            Transaction.user_id == user_id, Transaction.is_income.is_(True),
            Transaction.date >= since))).scalars().all()
    return int(sum(total) / 3)


@router.post("/goals", response_model=dict, status_code=201)
async def create_goal(body: GoalCreate, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    goal = Goal(user_id=user.id, **body.model_dump())
    db.add(goal)
    await db.flush()
    return GoalOut.model_validate(goal).model_dump()


@router.post("/goals/{goal_id}/contribute", response_model=GoalOut)
async def contribute_goal(goal_id: uuid.UUID, body: GoalContributionIn,
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    goal = await db.get(Goal, goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(404, "Goal not found")
    goal.saved_minor += body.amount_minor
    from datetime import datetime

    from app.db.base import utcnow

    if goal.saved_minor >= goal.target_minor and not goal.completed_at:
        goal.completed_at = utcnow()
    await db.flush()
    return goal


# ── Debts ───────────────────────────────────────────────────────────────

@router.get("/debts")
async def list_debts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Debt).where(Debt.user_id == user.id))).scalars().all()
    return [{"id": d.id.__str__(), "name": d.name, "principal_minor": d.principal_minor,
             "apr_bps": d.apr_bps, "min_payment_minor": d.min_payment_minor} for d in rows]


@router.post("/debts", status_code=201)
async def create_debt(body: DebtCreate, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    debt = Debt(user_id=user.id, **body.model_dump())
    db.add(debt)
    await db.flush()
    return {"id": debt.id.__str__()}


@router.get("/debts/payoff-schedule")
@router.get("/debts/payoff-plan")
async def debt_payoff_schedule(strategy: str = "avalanche", extra_payment_minor: int = 0,
                               user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """Payoff schedule for chosen strategy (avalanche or snowball)."""
    from app.services.goals_debt import compare_strategies, simulate_payoff

    rows = (await db.execute(select(Debt).where(Debt.user_id == user.id))).scalars().all()
    payload = [{"name": d.name, "principal_minor": d.principal_minor,
                "apr_bps": d.apr_bps, "min_payment_minor": d.min_payment_minor} for d in rows]
    if strategy in ("compare", "both"):
        return compare_strategies(payload, extra_payment_minor)
    return simulate_payoff(payload, extra_payment_minor, strategy=strategy)


@router.post("/debts/payoff-plan", response_model=dict)
async def payoff_plan(body: dict, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """Simulate snowball vs avalanche across all tracked debts."""
    from app.services.goals_debt import compare_strategies

    rows = (await db.execute(select(Debt).where(Debt.user_id == user.id))).scalars().all()
    payload = [{"name": d.name, "principal_minor": d.principal_minor,
                "apr_bps": d.apr_bps, "min_payment_minor": d.min_payment_minor} for d in rows]
    extra = int(body.get("extra_payment_minor", 0))
    return compare_strategies(payload, extra)


# ── Forecasting ─────────────────────────────────────────────────────────

@router.get("/forecasting/cash-flow")
async def cash_flow_forecast(user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    """Cash-flow forecasting with Holt's linear trend, 30d/90d projections, and runway analysis."""
    from app.models import Account
    from app.services.forecaster import forecast_net_flow, runway_months
    from app.services.txn_service import monthly_flows

    # 1. Total current balance across depository and cash accounts
    accounts = (await db.execute(
        select(Account).where(Account.user_id == user.id, Account.archived.is_(False)))).scalars().all()
    current_balance_minor = sum(a.balance_minor for a in accounts)

    # 2. Historical monthly cash flows
    flows = await monthly_flows(db, user.id, months=12)
    historical_trend = [
        {
            "month": f["month"],
            "income_minor": f["income_minor"],
            "expense_minor": f["expense_minor"],
            "net_flow_minor": f["income_minor"] - f["expense_minor"],
        }
        for f in flows
    ]

    monthly_nets = [h["net_flow_minor"] for h in historical_trend]
    fc = forecast_net_flow(monthly_nets, horizon=6)
    forecast_30d = fc["forecast"][0] if fc["forecast"] else 0
    forecast_90d = sum(fc["forecast"][:3]) if len(fc["forecast"]) >= 3 else 0
    runway = runway_months(current_balance_minor, fc["forecast"])

    return {
        "current_balance_minor": current_balance_minor,
        "historical_trend": historical_trend,
        "forecast_30d": forecast_30d,
        "forecast_90d": forecast_90d,
        "forecast_monthly": fc["forecast"],
        "confidence_interval": {
            "upper": fc["upper"],
            "lower": fc["lower"],
        },
        "runway_months": runway,
        "trend_per_month": fc["trend_per_month"],
        "residual_sigma": fc["residual_sigma"],
    }


# ── Alerts ──────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(unread_only: bool = False, limit: int = 50,
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    q = select(Alert).where(Alert.user_id == user.id)
    if unread_only:
        q = q.where(Alert.read_at.is_(None))
    return (await db.execute(q.order_by(Alert.created_at.desc()).limit(limit))).scalars().all()


@router.post("/alerts/{alert_id}/read", status_code=204)
async def read_alert(alert_id: uuid.UUID, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if alert and alert.user_id == user.id:
        from datetime import UTC, datetime

        alert.read_at = datetime.now(UTC)
    return None


@router.post("/alerts/scan-duplicate-subscriptions")
async def scan_dupes(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """On-demand duplicate-subscription scan + alert creation."""
    from app.services.anomaly import scan_subscription_duplicates
    from app.services.subscriptions import detect_subscriptions

    txns = (await db.execute(
        select(Transaction).where(Transaction.user_id == user.id,
                                  Transaction.is_income.is_(False))
        .order_by(Transaction.date.desc()).limit(600))).scalars().all()
    detected = detect_subscriptions([
        {"merchant_norm": t.merchant_norm, "amount_minor": t.amount_minor,
         "currency": t.currency, "date": t.date, "display_name": t.merchant_raw}
        for t in txns])
    payload = [s.__dict__ | {"first_seen": s.first_seen.isoformat(),
                             "last_seen": s.last_seen.isoformat()}
               for s in detected]
    alerts = await scan_subscription_duplicates(db, user.id, payload)
    return {"subscriptions_found": len(detected), "duplicate_alerts": len(alerts)}
