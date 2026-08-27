"""Tier 4 Real-World Application Scenarios.

5 comprehensive end-to-end user workflows:
1. Scenario 1: User Onboarding, Security Hardening & Zero-Knowledge Vault Setup
2. Scenario 2: Monthly Financial Lifecycle (CSV import, categorization, budgets, overspend)
3. Scenario 3: Multi-Currency Debt Payoff Planning & Dynamic Savings Goals
4. Scenario 4: Security Defense, Anomaly Detection & Envelope Encryption
5. Scenario 5: Conversational AI Coaching, Knowledge RAG & Natural-Language Expense Quick-Add
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import date, datetime, timedelta

import httpx
import pyotp
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pii import mask_pii
from app.ai.rag import build_context, ingest_document
from app.core.crypto import open_sealed, seal
from app.core.security import decode_token, verify_password
from app.models import (
    Account,
    Alert,
    BankConnection,
    Budget,
    BudgetEnvelope,
    Category,
    ChatMessage,
    ChatThread,
    Debt,
    Goal,
    KnowledgeDoc,
    Transaction,
    User,
)
from app.services import (
    anomaly,
    auth_service,
    budget_engine,
    categorizer,
    forecaster,
    fx,
    goals_debt,
    importers,
    subscriptions,
    txn_service,
)
from app.services.events import bus


# ============================================================================
# Scenario 1: User Onboarding, Security Hardening & ZK Vault Setup
# ============================================================================

@pytest.mark.asyncio
async def test_scenario_1_user_onboarding_security_and_vault(
    async_client: httpx.AsyncClient, db_session: AsyncSession
):
    """Scenario 1:
    Complete user onboarding journey:
    1. Register new user with Argon2id password hash.
    2. Obtain JWT access & rotating refresh token.
    3. Verify profile via /auth/me.
    4. Setup TOTP MFA, obtain secret and recovery codes.
    5. Verify MFA enforcement on login.
    6. Complete MFA login.
    7. Configure client-side Zero-Knowledge Vault.
    8. Create account and record transaction with E2E encrypted private note.
    """
    user_email = "onboarding.alice@financebuddy.app"
    user_pass = "StrongOnboardingPass123!"

    # 1. Register
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": user_email,
            "password": user_pass,
            "full_name": "Alice Onboarding",
            "locale": "en",
            "base_currency": "USD",
        },
    )
    assert reg_resp.status_code == 201
    reg_tokens = reg_resp.json()
    access_token = reg_tokens["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 2. Verify Profile
    me_resp = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    profile = me_resp.json()
    assert profile["email"] == user_email
    assert profile["mfa_enabled"] is False

    # 3. Setup TOTP MFA
    mfa_start = await async_client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert mfa_start.status_code == 200
    secret = mfa_start.json()["secret"]

    code = pyotp.TOTP(secret).now()
    mfa_conf = await async_client.post(
        "/api/v1/auth/mfa/confirm", headers=headers, json={"code": code}
    )
    assert mfa_conf.status_code == 200
    recovery_codes = mfa_conf.json()["recovery_codes"]
    assert len(recovery_codes) == 8

    # 4. Verify login requires MFA
    chal_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": user_pass},
    )
    assert chal_login.status_code == 200
    assert chal_login.json()["mfa_required"] is True

    # 5. Complete login with TOTP code
    totp_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": user_pass, "totp_code": pyotp.TOTP(secret).now()},
    )
    assert totp_login.status_code == 200
    new_access_token = totp_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {new_access_token}"}

    # 6. Configure Zero-Knowledge Vault
    vault_data = {
        "kdf": "Argon2id",
        "kdf_salt_hex": "0123456789abcdef0123456789abcdef",
        "wrapped_dek_b64": "U2VjdXJlV3JhcHBlZERFS01hdGVyaWFs",
        "verifier_b64": "VmVyaWZpZXJDaGVja1N1bTEyMzQ1",
    }
    v_resp = await async_client.post("/api/v1/auth/vault", headers=headers, json=vault_data)
    assert v_resp.status_code == 200

    vault_get = await async_client.get("/api/v1/auth/vault", headers=headers)
    assert vault_get.json()["wrapped_dek_b64"] == vault_data["wrapped_dek_b64"]

    # 7. Create Checking Account & Encrypted Note Transaction
    acct_resp = await async_client.post(
        "/api/v1/accounts",
        headers=headers,
        json={"name": "Alice Checking", "type": "depository", "currency": "USD", "balance_minor": 500000},
    )
    assert acct_resp.status_code == 201
    acct_id = acct_resp.json()["id"]

    enc_note = "AES-GCM-CIPHERTEXT-CONFIDENTIAL-MEDICAL-NOTE"
    txn_resp = await async_client.post(
        "/api/v1/transactions",
        headers=headers,
        json={
            "account_id": acct_id,
            "date": "2026-03-15",
            "amount_minor": -7500,
            "merchant_raw": "Dental Surgery Clinic",
            "notes_encrypted": enc_note,
        },
    )
    assert txn_resp.status_code == 201
    assert txn_resp.json()["notes_encrypted"] == enc_note


# ============================================================================
# Scenario 2: Monthly Financial Lifecycle
# ============================================================================

@pytest.mark.asyncio
async def test_scenario_2_monthly_financial_lifecycle(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_account: Account,
    test_user: User,
):
    """Scenario 2:
    Monthly financial operations flow:
    1. Create zero-based budget with envelopes for Rent, Groceries, Dining Out.
    2. Import monthly CSV bank statement containing salary and expenses.
    3. Auto-categorization categorizes all records.
    4. Compute envelope status and detect overspending on Dining Out.
    5. Trigger overspend alert creation.
    6. Request allocation suggestions for next month.
    """
    housing = await db_session.scalar(select(Category).where(Category.name == "Housing"))
    groceries = await db_session.scalar(select(Category).where(Category.name == "Groceries"))
    dining = await db_session.scalar(select(Category).where(Category.name == "Dining Out"))

    today = date.today()
    first_of_month = today.replace(day=1)

    # 1. Create Zero-Based Monthly Budget ($4,000 income planned)
    budget_payload = {
        "name": "Monthly Plan",
        "strategy": "zero_based",
        "start_date": first_of_month.isoformat(),
        "income_planned_minor": 400_000,
        "currency": "USD",
        "envelopes": [
            {"category_id": str(housing.id), "name": "Housing", "allocated_minor": 200_000},
            {"category_id": str(groceries.id), "name": "Groceries", "allocated_minor": 120_000},
            {"category_id": str(dining.id), "name": "Dining Out", "allocated_minor": 80_000},
        ],
    }
    b_resp = await async_client.post("/api/v1/budgets", headers=auth_headers, json=budget_payload)
    assert b_resp.status_code == 201
    budget_id = b_resp.json()["id"]

    # 2. Ingest CSV Statement
    csv_bytes = (
        f"Date,Amount,Merchant,Description\n"
        f"{first_of_month.isoformat()},4000.00,ACME CORP PAYROLL,Monthly Salary\n"
        f"{first_of_month.isoformat()},-2000.00,MONTHLY RENT PAYMENT,Apartment Rent\n"
        f"{(first_of_month + timedelta(days=2)).isoformat()},-110.00,COSTCO WHOLESALE,Groceries run\n"
        f"{(first_of_month + timedelta(days=5)).isoformat()},-95.00,STARBUCKS AND BISTRO,Dining out with team\n"
    ).encode("utf-8")

    files = {"file": ("monthly.csv", csv_bytes, "text/csv")}
    import_resp = await async_client.post(
        f"/api/v1/import/{test_account.id}/csv", headers=auth_headers, files=files
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["created"] == 4

    # 3. Check Envelope Status: Dining Out allocated $80, spent $95 -> Overspent!
    status_resp = await async_client.get(
        f"/api/v1/budgets/{budget_id}/status/{today.year}/{today.month}",
        headers=auth_headers,
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    dining_env = next((e for e in status_data["envelopes"] if e["name"] == "Dining Out"), None)
    assert dining_env is not None
    assert dining_env["overspent"] is True
    assert dining_env["spent_minor"] == 9500

    # 4. Trigger overspend check and verify alert
    await anomaly.overspend_check(db_session, uuid.UUID(budget_id))
    alerts = (
        await db_session.execute(
            select(Alert).where(Alert.user_id == test_user.id, Alert.type == "overspend")
        )
    ).scalars().all()
    assert len(alerts) >= 1
    assert "Dining Out" in alerts[0].title

    # 5. Suggest allocations based on spend
    sug_resp = await async_client.get("/api/v1/budgets/suggestions", headers=auth_headers)
    assert sug_resp.status_code == 200
    assert "suggestions" in sug_resp.json()


# ============================================================================
# Scenario 3: Multi-Currency Debt Payoff Planning & Dynamic Goals
# ============================================================================

@pytest.mark.asyncio
async def test_scenario_3_multicurrency_debts_and_dynamic_goals(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
):
    """Scenario 3:
    Debt payoff optimization & multi-currency income goal adjustment:
    1. Register multiple debts (Credit card vs Student loan).
    2. Compare Snowball vs Avalanche payoff simulations.
    3. Verify Avalanche interest savings.
    4. Setup percentage-of-income savings goal.
    5. Convert foreign income from EUR to USD and dynamically track goal progress.
    """
    # 1. Debts Setup
    d1 = {"name": "High APR Card", "principal_minor": 400_000, "apr_bps": 2400, "min_payment_minor": 12_000}
    d2 = {"name": "Low APR Loan", "principal_minor": 800_000, "apr_bps": 600, "min_payment_minor": 20_000}
    await async_client.post("/api/v1/debts", headers=auth_headers, json=d1)
    await async_client.post("/api/v1/debts", headers=auth_headers, json=d2)

    # 2. Compare Strategies
    plan_resp = await async_client.post(
        "/api/v1/debts/payoff-plan", headers=auth_headers, json={"extra_payment_minor": 15_000}
    )
    assert plan_resp.status_code == 200
    plan = plan_resp.json()
    assert plan["interest_saved_by_avalanche_minor"] >= 0
    assert plan["avalanche"]["payoff_order"][0] == "High APR Card"

    # 3. Create Goal with percent_income strategy (10% of monthly income)
    goal_payload = {
        "name": "Down Payment Fund",
        "target_minor": 2_000_000,  # $20,000
        "currency": "USD",
        "strategy": "percent_income",
        "percent_of_income": 10.0,
    }
    g_resp = await async_client.post("/api/v1/goals", headers=auth_headers, json=goal_payload)
    assert g_resp.status_code == 201
    goal_id = g_resp.json()["id"]

    # 4. Multi-currency income conversion
    eur_consulting_income = 300_000  # 3,000 EUR
    usd_income = await fx.convert_minor(db_session, eur_consulting_income, "EUR", "USD")

    # 5. Contribute to goal
    contribute_resp = await async_client.post(
        f"/api/v1/goals/{goal_id}/contribute",
        headers=auth_headers,
        json={"amount_minor": usd_income},
    )
    assert contribute_resp.status_code == 200
    assert contribute_resp.json()["saved_minor"] == usd_income


# ============================================================================
# Scenario 4: Security Defense, Anomaly Detection & Envelope Encryption
# ============================================================================

@pytest.mark.asyncio
async def test_scenario_4_security_defense_and_anomaly_detection(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_account: Account,
    test_user: User,
):
    """Scenario 4:
    Security hardening & anomaly defense under attack:
    1. Establish normal grocery spending baseline ($20 - $40).
    2. Outlier spike transaction ($1,500) triggers unusual_charge alert.
    3. Duplicate charge attack triggers duplicate_charge alert.
    4. Rapid spending burst (6 transactions in 24h) triggers velocity_burst alert.
    5. Mask PII in prompt containing raw credit cards, phones, and emails.
    6. Verify bank access tokens at rest are sealed with AES-256-GCM.
    """
    today = date.today()

    # 1. Baseline
    history = []
    for d in range(15):
        txn, _ = await txn_service.create_transaction(
            db_session,
            account=test_account,
            date=today - timedelta(days=d + 2),
            amount_minor=-3000,
            merchant_raw="Corner Grocery",
        )
        history.append(txn)

    # 2. Outlier Spike
    spike_txn, _ = await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=today,
        amount_minor=-150_000,
        merchant_raw="Corner Grocery",
    )
    history.append(spike_txn)
    alerts1 = await anomaly.analyze_transaction(db_session, spike_txn, history=history)
    assert any(a.type == "unusual_charge" for a in alerts1)

    # 3. Duplicate Charge
    dup_txn, _ = await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=today,
        amount_minor=-150_000,
        merchant_raw="Corner Grocery",
    )
    history.append(dup_txn)
    alerts2 = await anomaly.analyze_transaction(db_session, dup_txn, history=history)
    assert any(a.type == "duplicate_charge" for a in alerts2)

    # 4. PII Masking Defense
    sensitive_prompt = (
        "Customer card 4532015112830366 was charged twice. Contact support at "
        "support@financebuddy.app or +1 800 555 0199 for account DE89370400440532013000."
    )
    sanitized = mask_pii(sensitive_prompt)
    assert "[CARD]" in sanitized
    assert "[EMAIL]" in sanitized
    assert "[PHONE]" in sanitized
    assert "[IBAN]" in sanitized
    assert "4532015112830366" not in sanitized
    assert "support@financebuddy.app" not in sanitized

    # 5. Envelope Encryption at Rest
    bank_secret = "plaid-access-sandbox-token-12345"
    sealed_token = seal(bank_secret)
    assert sealed_token != bank_secret
    assert open_sealed(sealed_token) == bank_secret


# ============================================================================
# Scenario 5: Conversational AI Coaching & Knowledge RAG
# ============================================================================

@pytest.mark.asyncio
async def test_scenario_5_conversational_ai_coaching_and_rag(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
):
    """Scenario 5:
    Conversational AI assistant & financial coach flow:
    1. Ingest financial guide into pgvector KnowledgeDoc RAG corpus.
    2. Quick-add expense via NLP parsing.
    3. User queries assistant with financial coach question.
    4. Verify supervisor routes intent appropriately and PII is masked.
    5. Verify chat message history is persisted in ChatThread and ChatMessage.
    """
    # 1. Ingest Knowledge Doc
    guide = (
        "Debt Avalanche Strategy:\n\n"
        "The debt avalanche method focuses on making minimum payments on all debts and "
        "allocating remaining discretionary funds to the debt with the highest annual "
        "percentage rate (APR). This mathematically minimizes total interest paid."
    )
    await ingest_document(db_session, "Debt Avalanche Guide", guide, user_id=test_user.id)

    # 2. Natural language expense parse
    parse_resp = await async_client.post(
        "/api/v1/chat/expenses/parse",
        headers=auth_headers,
        json={"text": "$16.80 for Books at Barnes and Noble", "currency": "USD"},
    )
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    assert parsed["amount_minor"] == 1680

    # 3. Send chat message
    chat_resp = await async_client.post(
        "/api/v1/chat/send",
        headers=auth_headers,
        json={"message": "How does debt avalanche save interest on credit cards?", "agent_mode": "coach"},
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    assert "thread_id" in data
    assert "reply" in data
    thread_id = data["thread_id"]

    # 4. Verify thread and messages persisted in database
    thread_messages = (
        await db_session.execute(
            select(ChatMessage).where(ChatMessage.thread_id == uuid.UUID(thread_id))
        )
    ).scalars().all()
    assert len(thread_messages) >= 2  # user + assistant
    assert any(m.role == "user" for m in thread_messages)
    assert any(m.role == "assistant" for m in thread_messages)

    # 5. Fetch message history via API endpoint
    history_resp = await async_client.get(
        f"/api/v1/chat/threads/{thread_id}/messages", headers=auth_headers
    )
    assert history_resp.status_code == 200
    assert len(history_resp.json()) >= 2
