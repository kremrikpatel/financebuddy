"""Tests for database seed script completeness and idempotency."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    Alert,
    Budget,
    BudgetEnvelope,
    Category,
    Debt,
    FxRate,
    Goal,
    RecurringSubscription,
    Transaction,
    User,
)
from app.seed import seed


@pytest.mark.asyncio
async def test_seed_populates_rich_dataset(db_session: AsyncSession):
    # Execute seed script
    await seed(db_session)

    # 1. System categories (20 standard categories)
    cat_count = await db_session.scalar(select(func.count(Category.id)).where(Category.user_id.is_(None)))
    assert cat_count >= 20

    # 2. Demo user
    demo = await db_session.scalar(select(User).where(User.email == "demo@financebuddy.app"))
    assert demo is not None
    assert demo.base_currency == "AUD"
    assert demo.is_active is True

    # 3. Multi-currency accounts
    accounts = (await db_session.execute(select(Account).where(Account.user_id == demo.id))).scalars().all()
    assert len(accounts) >= 5
    currencies = {a.currency for a in accounts}
    assert "AUD" in currencies
    assert "USD" in currencies
    assert "EUR" in currencies
    assert "GBP" in currencies
    assert "JPY" in currencies

    # 4. Realistic transaction records (100+)
    txn_count = await db_session.scalar(select(func.count(Transaction.id)).where(Transaction.user_id == demo.id))
    assert txn_count >= 100

    # 5. Budgets & Envelopes
    budgets = (await db_session.execute(select(Budget).where(Budget.user_id == demo.id))).scalars().all()
    assert len(budgets) >= 1
    envelopes = (await db_session.execute(select(BudgetEnvelope).where(BudgetEnvelope.budget_id == budgets[0].id))).scalars().all()
    assert len(envelopes) >= 5

    # 6. Goals
    goals = (await db_session.execute(select(Goal).where(Goal.user_id == demo.id))).scalars().all()
    assert len(goals) >= 3
    goal_names = {g.name for g in goals}
    assert "Emergency Fund" in goal_names
    assert "House Deposit" in goal_names

    # 7. Debts
    debts = (await db_session.execute(select(Debt).where(Debt.user_id == demo.id))).scalars().all()
    assert len(debts) >= 2
    debt_names = {d.name for d in debts}
    assert "Rewards Credit Card" in debt_names

    # 8. Subscriptions
    subs = (await db_session.execute(select(RecurringSubscription).where(RecurringSubscription.user_id == demo.id))).scalars().all()
    assert len(subs) >= 4
    sub_names = {s.merchant_norm for s in subs}
    assert "netflix" in sub_names
    assert "spotify" in sub_names

    # 9. Alerts
    alerts = (await db_session.execute(select(Alert).where(Alert.user_id == demo.id))).scalars().all()
    assert len(alerts) >= 3
    alert_types = {a.type for a in alerts}
    assert "spending_spike" in alert_types
    assert "duplicate_subscription" in alert_types

    # 10. FX rates
    fx_count = await db_session.scalar(select(func.count(FxRate.base)))
    assert fx_count >= 10

    # 11. Idempotency test (running seed again does not duplicate accounts or crash)
    await seed(db_session)
    acc_count_2 = await db_session.scalar(select(func.count(Account.id)).where(Account.user_id == demo.id))
    assert acc_count_2 == len(accounts)
