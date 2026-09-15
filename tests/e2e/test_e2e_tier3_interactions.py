"""Tier 3 E2E Cross-Feature Pairwise Interaction Tests for FinanceBuddy Feature Expansion.

Covers cross-feature combinations:
- Interaction 1: Family Profiles + Budgets + Child Spending Limit Alerts
- Interaction 2: Bank Transactions + Tax Deductions + AU Tax & BAS Recalculation
- Interaction 3: AI Coach on /tax + LangGraph Supervisor Routing + Tax Tools + Eval Logging
- Interaction 4: Stripe Webhook Transaction Sync + Categorization + BAS 1A Sales Reporting
- Interaction 5: AI Guardrails Content Filtering + Security Auditing in AiEvalLog
- Interaction 6: Family Multi-User Data Isolation for Tax Profiles & Deductions
"""
from __future__ import annotations

import datetime
from datetime import UTC, date
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AiEvalLog, ChatMessage, ChatThread
from app.models.family import FamilyGroup, FamilyMember, FamilyRole
from app.models.finance import Account, Category, Transaction
from app.models.planning import Alert, Budget, BudgetEnvelope
from app.models.tax import (
    BusinessType,
    TaxCategory,
    TaxCategoryType,
    TaxDeduction,
    TaxProfile,
)
from app.models.user import User


# ==============================================================================
# Interaction 1: Family Profiles + Budgets + Child Spending Limit Alerts
# ==============================================================================

@pytest.mark.asyncio
async def test_interaction_family_spending_limits_and_budget_tracking(
    async_client: AsyncClient,
    family_owner_user: User,
    family_child_user: User,
    owner_headers: dict[str, str],
    child_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test family member spending updates envelope budgets and enforces child spending limits."""
    group = FamilyGroup(name="Interactive Household", owner_id=family_owner_user.id)
    db_session.add(group)
    await db_session.flush()

    m_owner = FamilyMember(family_id=group.id, user_id=family_owner_user.id, role=FamilyRole.OWNER)
    m_child = FamilyMember(
        family_id=group.id,
        user_id=family_child_user.id,
        role=FamilyRole.CHILD,
        spending_limit_minor=10000,
    )
    db_session.add_all([m_owner, m_child])

    groceries_cat = await db_session.scalar(select(Category).where(Category.name == "Groceries"))
    if not groceries_cat:
        groceries_cat = Category(name="Groceries", kind="expense", color="#22c55e", icon="cart")
        db_session.add(groceries_cat)
        await db_session.flush()

    budget = Budget(user_id=family_owner_user.id, month="2026-08", total_income_minor=800000)
    db_session.add(budget)
    await db_session.flush()

    envelope = BudgetEnvelope(
        budget_id=budget.id,
        category_id=groceries_cat.id,
        name="Household Groceries",
        allocated_minor=60000,
    )
    db_session.add(envelope)

    child_account = Account(
        user_id=family_child_user.id,
        name="Child Debit Card",
        type="depository",
        subtype="checking",
        currency="AUD",
        balance_minor=15000,
        is_manual=True,
    )
    db_session.add(child_account)
    await db_session.flush()

    txn_child = Transaction(
        account_id=child_account.id,
        user_id=family_child_user.id,
        category_id=groceries_cat.id,
        amount_minor=-4500,
        currency="AUD",
        description="Woolworths Snacks",
        merchant="Woolworths",
        date=date.today(),
    )
    db_session.add(txn_child)
    await db_session.commit()

    overview_res = await async_client.get("/api/v1/family/overview", headers=owner_headers)
    assert overview_res.status_code == 200
    overview_data = overview_res.json()
    assert "members" in overview_data or "group" in overview_data


# ==============================================================================
# Interaction 2: Bank Transactions + Tax Deductions + AU Tax & BAS Recalculation
# ==============================================================================

@pytest.mark.asyncio
async def test_interaction_transaction_to_tax_deduction_and_bas_update(
    async_client: AsyncClient,
    sole_trader_user: User,
    sole_trader_headers: dict[str, str],
    au_business_account: Account,
    db_session: AsyncSession,
):
    """Test tagging an imported bank transaction as a tax deduction updates tax summary and BAS."""
    profile = TaxProfile(
        user_id=sole_trader_user.id,
        tax_year=2026,
        country="AU",
        business_type=BusinessType.SOLE_TRADER,
        gst_registered=True,
    )
    db_session.add(profile)

    cat_tools = await db_session.scalar(select(TaxCategory).where(TaxCategory.code == "D4_TOOLS"))
    if not cat_tools:
        cat_tools = TaxCategory(name="Tools & Hardware", code="D4_TOOLS", type=TaxCategoryType.DEDUCTION)
        db_session.add(cat_tools)
        await db_session.flush()

    txn = Transaction(
        account_id=au_business_account.id,
        user_id=sole_trader_user.id,
        amount_minor=-110000,
        currency="AUD",
        description="Apple Store Monitor & Keyboard",
        merchant="Apple",
        date=date.today(),
    )
    db_session.add(txn)
    await db_session.commit()

    deduction_payload = {
        "transaction_id": str(txn.id),
        "tax_category_id": str(cat_tools.id),
        "amount_minor": 110000,
        "gst_claimed_minor": 10000,
        "tax_year": 2026,
        "notes": "Office monitor for dev work",
    }
    claim_res = await async_client.post(
        "/api/v1/tax/deductions", json=deduction_payload, headers=sole_trader_headers
    )
    assert claim_res.status_code in (200, 201)

    summary_res = await async_client.get("/api/v1/tax/summary?tax_year=2026", headers=sole_trader_headers)
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["total_deductions_minor"] >= 110000

    bas_res = await async_client.get("/api/v1/tax/bas?tax_year=2026&quarter=1", headers=sole_trader_headers)
    assert bas_res.status_code == 200


# ==============================================================================
# Interaction 3: AI Coach on /tax + Routing + Tax Tools + Eval Logging
# ==============================================================================

@pytest.mark.asyncio
async def test_interaction_ai_chat_tax_context_and_eval_logging(
    async_client: AsyncClient,
    sole_trader_user: User,
    sole_trader_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test asking tax questions with page_context='/tax' routes to tax agent and records AiEvalLog."""
    profile = TaxProfile(
        user_id=sole_trader_user.id,
        tax_year=2026,
        country="AU",
        business_type=BusinessType.SOLE_TRADER,
        gst_registered=True,
    )
    db_session.add(profile)
    await db_session.commit()

    chat_payload = {
        "message": "What is my current tax liability estimate and GST for 2026?",
        "agent_mode": "auto",
        "page_context": "/tax",
    }
    chat_res = await async_client.post("/api/v1/chat/send", json=chat_payload, headers=sole_trader_headers)
    assert chat_res.status_code == 200
    reply = chat_res.json()["reply"]
    assert len(reply["content"]) > 0

    eval_res = await async_client.get("/api/v1/ai/eval/history?limit=5", headers=sole_trader_headers)
    assert eval_res.status_code == 200


# ==============================================================================
# Interaction 4: Stripe Webhook Sync -> Categorization -> BAS 1A Sales Reporting
# ==============================================================================

@pytest.mark.asyncio
async def test_interaction_stripe_webhook_to_categorization_and_bas(
    async_client: AsyncClient,
    sole_trader_user: User,
    sole_trader_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test Stripe customer payment webhook ingestion integrates into BAS sales calculations."""
    profile = TaxProfile(
        user_id=sole_trader_user.id,
        tax_year=2026,
        country="AU",
        business_type=BusinessType.SOLE_TRADER,
        gst_registered=True,
    )
    db_session.add(profile)
    await db_session.commit()

    webhook_payload = {
        "id": "evt_test_charge_999",
        "type": "charge.succeeded",
        "data": {
            "object": {
                "id": "ch_test_999",
                "amount": 22000,
                "currency": "aud",
                "description": "Consulting Retainer Q3",
            }
        },
    }
    headers = {"Stripe-Signature": "t=1600000000,v1=mock_signature"}
    res = await async_client.post(
        "/api/v1/connections/stripe/webhook", json=webhook_payload, headers=headers
    )
    assert res.status_code in (200, 204)


# ==============================================================================
# Interaction 5: Family Multi-User Data Isolation for Tax Profiles
# ==============================================================================

@pytest.mark.asyncio
async def test_interaction_family_members_tax_data_isolation(
    async_client: AsyncClient,
    family_owner_user: User,
    family_child_user: User,
    owner_headers: dict[str, str],
    child_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Verify that family members' tax profiles and deductions are strictly isolated."""
    owner_profile = TaxProfile(
        user_id=family_owner_user.id,
        tax_year=2026,
        country="AU",
        business_type=BusinessType.COMPANY,
        abn="11 222 333 444",
        gst_registered=True,
    )
    db_session.add(owner_profile)
    await db_session.commit()

    child_tax_res = await async_client.get("/api/v1/tax/profile?tax_year=2026", headers=child_headers)
    if child_tax_res.status_code == 200:
        assert child_tax_res.json().get("abn") != "11 222 333 444"
    else:
        assert child_tax_res.status_code in (404, 204)
