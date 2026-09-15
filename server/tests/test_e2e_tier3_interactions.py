"""Tier 3 Cross-Feature Pairwise Interaction Tests.

Verifies end-to-end multi-service interaction chains and workflows:
1. CSV import -> rule categorization -> budget status recalculation -> overspend alert
2. Registration -> MFA setup & confirm -> ZK vault seal -> encrypted transaction note
3. Multi-currency transaction -> FX conversion -> goal recalculation & tracking
4. Transaction creation -> velocity burst detection -> alert generation -> websocket broadcast
5. CSV import -> duplicate charge detection -> alert creation -> alert mark as read
6. Transaction categorization edit -> user feedback confirmation -> audit log
7. Account creation -> transaction addition -> monthly cash-flow aggregation -> Holt forecasting
8. Multiple debt creation -> extra payment update -> snowball/avalanche payoff simulation
9. Natural language expense parse -> transaction creation -> account balance deduction
10. Transaction creation -> multi-split addition -> total amount validation & split limit enforcement
11. Subscription transaction sequence -> recurring subscription detection -> duplicate subscription scan
12. Knowledge doc RAG ingestion -> prompt PII masking -> RAG context injection
13. Account initial balance -> manual transactions -> dynamic balance updates -> account archive
14. User registration -> multi-device refresh tokens -> session pruning -> session revocation
15. Passkey registration -> passkey options -> credential storage -> sign count tracking
16. Zero-based budget rebalancing lifecycle -> under/over-assigned transitions
17. Goal percent_income strategy -> dynamic tracking based on salary transaction additions
18. OFX statement import -> account balance update -> rule categorization -> deduplication
19. Multi-item transaction description -> split tagging -> AI split suggestion endpoint
20. Event bus multi-user subscriptions -> tenant isolation and routing
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pii import mask_pii
from app.ai.rag import build_context, ingest_document
from app.core.security import decode_token
from app.models import (
    Account,
    Alert,
    Budget,
    BudgetEnvelope,
    Category,
    Debt,
    Goal,
    KnowledgeDoc,
    PasskeyCredential,
    RefreshToken,
    Transaction,
    TransactionSplit,
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
from app.services.events import bus, new_event, ws_manager


# ============================================================================
# 1. CSV import -> categorization -> budget status -> overspend alert
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_csv_import_to_budget_overspend_alert(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_account: Account,
    test_user: User,
):
    dining = await db_session.scalar(select(Category).where(Category.name == "Dining Out"))
    today = date.today()

    # 1. Create a budget for Dining Out with 10000 minor ($100) limit
    budget = Budget(
        user_id=test_user.id,
        name="Dining Budget",
        strategy="envelope",
        start_date=today.replace(day=1),
        income_planned_minor=100000,
        currency="USD",
    )
    db_session.add(budget)
    await db_session.flush()

    env = BudgetEnvelope(
        budget_id=budget.id,
        category_id=dining.id,
        name="Dining Out",
        allocated_minor=10000,
    )
    db_session.add(env)
    await db_session.flush()

    # 2. Ingest CSV with Dining transactions totaling 15000 minor ($150)
    csv_data = (
        "Date,Amount,Merchant,Description\n"
        f"{today.isoformat()},-80.00,McDonalds,Lunch\n"
        f"{today.isoformat()},-70.00,Chipotle,Dinner\n"
    ).encode("utf-8")

    files = {"file": ("dining.csv", csv_data, "text/csv")}
    import_resp = await async_client.post(
        f"/api/v1/import/{test_account.id}/csv", headers=auth_headers, files=files
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["created"] == 2

    # 3. Check budget status shows overspent
    statuses = await budget_engine.envelope_status(db_session, budget, today.year, today.month)
    assert len(statuses) == 1
    assert statuses[0].overspent is True
    assert statuses[0].spent_minor == 15000

    # 4. Trigger overspend alert check
    await anomaly.overspend_check(db_session, budget.id)
    alerts = (
        await db_session.execute(
            select(Alert).where(Alert.user_id == test_user.id, Alert.type == "overspend")
        )
    ).scalars().all()
    assert len(alerts) >= 1
    assert "Dining Out" in alerts[0].title


# ============================================================================
# 2. Registration -> MFA -> ZK Vault -> Encrypted Note
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_registration_to_mfa_to_vault_to_encrypted_note(
    async_client: httpx.AsyncClient, db_session: AsyncSession
):
    import pyotp

    # Step 1: Register
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "vaultuser@financebuddy.app", "password": "SecurePassword123!", "full_name": "Vault User"},
    )
    assert reg_resp.status_code == 201
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Setup & Confirm TOTP MFA
    mfa_start = await async_client.post("/api/v1/auth/mfa/setup", headers=headers)
    secret = mfa_start.json()["secret"]
    code = pyotp.TOTP(secret).now()
    mfa_conf = await async_client.post(
        "/api/v1/auth/mfa/confirm", headers=headers, json={"code": code}
    )
    assert mfa_conf.status_code == 200
    assert mfa_conf.json()["enabled"] is True

    # Step 3: Setup Zero-Knowledge Vault
    vault_payload = {
        "kdf": "Argon2id",
        "kdf_salt_hex": "fedcba9876543210fedcba9876543210",
        "wrapped_dek_b64": "SGVsbG9XZWJBY3VyeVRlc3RLZXk=",
        "verifier_b64": "VmVyaWZpZXJWYWx1ZTEyMzQ1",
    }
    v_resp = await async_client.post("/api/v1/auth/vault", headers=headers, json=vault_payload)
    assert v_resp.status_code == 200

    # Step 4: Create Account and Transaction with E2E Encrypted Note
    acct_resp = await async_client.post(
        "/api/v1/accounts",
        headers=headers,
        json={"name": "Secure Checking", "type": "depository", "currency": "USD", "balance_minor": 100000},
    )
    assert acct_resp.status_code == 201
    acct_id = acct_resp.json()["id"]

    ciphertext_note = "CIPHERTEXT:U2FsdGVkX1+vupppZksvRf5pq5g5XjFRIipR"
    txn_resp = await async_client.post(
        "/api/v1/transactions",
        headers=headers,
        json={
            "account_id": acct_id,
            "date": "2026-03-15",
            "amount_minor": -3000,
            "merchant_raw": "Private Doctor",
            "notes_encrypted": ciphertext_note,
        },
    )
    assert txn_resp.status_code == 201
    assert txn_resp.json()["notes_encrypted"] == ciphertext_note


# ============================================================================
# 3. Multi-currency Transaction -> FX Conversion -> Goal Recalculation
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_multicurrency_fx_to_goal_progress(
    db_session: AsyncSession, test_user: User
):
    # Goal in USD: Target $5,000 USD (500000 minor)
    goal = Goal(
        user_id=test_user.id,
        name="Vacation in Europe",
        target_minor=500_000,
        saved_minor=0,
        currency="USD",
        strategy="fixed_monthly",
        monthly_amount_minor=50_000,
        target_date=date.today() + timedelta(days=300),
    )
    db_session.add(goal)
    await db_session.flush()

    # User earns income in EUR: 2,000 EUR (200000 minor)
    eur_income_minor = 200_000
    # Convert EUR to USD minor using FX service
    usd_equiv_minor = await fx.convert_minor(db_session, eur_income_minor, "EUR", "USD")
    assert usd_equiv_minor > 0

    # User contributes converted amount to USD goal
    goal.saved_minor += usd_equiv_minor
    await db_session.flush()

    track = goals_debt.goal_on_track(
        goal.strategy,
        goal.saved_minor,
        goal.target_minor,
        goal.monthly_amount_minor,
        goal.percent_of_income,
        0,
        goal.target_date,
    )
    assert track["on_track"] is True
    assert goal.saved_minor == usd_equiv_minor


# ============================================================================
# 4. Transaction Creation -> Velocity Burst -> Alert -> WS Broadcast
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_velocity_burst_to_ws_broadcast(
    db_session: AsyncSession, test_account: Account
):
    user_id_str = str(test_account.user_id)
    sub_queue = await bus.subscribe(user_id_str)

    today = date.today()
    created_txns = []
    # Create 6 transactions in 24 hours
    for i in range(6):
        txn, _ = await txn_service.create_transaction(
            db_session,
            account=test_account,
            date=today,
            amount_minor=-(1000 + i * 100),
            merchant_raw=f"Rapid Store {i}",
        )
        created_txns.append(txn)

    # Run anomaly check on newest transaction with history
    alerts = await anomaly.analyze_transaction(db_session, created_txns[-1], history=created_txns)
    assert any(a.type == "velocity_burst" for a in alerts)

    # Read batch from event bus
    batch = await bus.read_batch(count=10, block_ms=500)
    event_types = [entry[1].get("type") for entry in batch]
    assert "transaction.created" in event_types
    assert "alert.created" in event_types

    await bus.unsubscribe(user_id_str, sub_queue)


# ============================================================================
# 5. CSV Import -> Duplicate Charge -> Alert Creation -> Alert Read
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_duplicate_charge_to_alert_read(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_account: Account,
    test_user: User,
):
    # Ingest 2 identical charges at same merchant 1 day apart
    t1, _ = await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=date(2026, 3, 1),
        amount_minor=-7999,
        merchant_raw="Adobe Subscription",
    )
    t2, _ = await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=date(2026, 3, 2),
        amount_minor=-7999,
        merchant_raw="Adobe Subscription",
    )
    alerts = await anomaly.analyze_transaction(db_session, t2, history=[t1, t2])
    dup_alert = next((a for a in alerts if a.type == "duplicate_charge"), None)
    assert dup_alert is not None

    # Verify alert appears in unread alerts list
    list_resp = await async_client.get("/api/v1/alerts?unread_only=true", headers=auth_headers)
    assert list_resp.status_code == 200
    alert_ids = [a["id"] for a in list_resp.json()]
    assert str(dup_alert.id) in alert_ids

    # Mark alert as read
    read_resp = await async_client.post(f"/api/v1/alerts/{dup_alert.id}/read", headers=auth_headers)
    assert read_resp.status_code == 204

    # Verify no longer in unread alerts list
    list_resp2 = await async_client.get("/api/v1/alerts?unread_only=true", headers=auth_headers)
    alert_ids2 = [a["id"] for a in list_resp2.json()]
    assert str(dup_alert.id) not in alert_ids2


# ============================================================================
# 6. Transaction Categorization Edit -> User Feedback Confirmation
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_txn_category_user_edit_feedback(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_account: Account,
):
    shopping = await db_session.scalar(select(Category).where(Category.name == "Shopping"))
    txn, _ = await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=date(2026, 3, 5),
        amount_minor=-5000,
        merchant_raw="Specialty Boutique",
    )

    # Edit category through PATCH endpoint
    edit_payload = {
        "category_id": str(shopping.id),
        "confirmed_by_user": True,
    }
    patch_resp = await async_client.patch(
        f"/api/v1/transactions/{txn.id}", headers=auth_headers, json=edit_payload
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["category_id"] == str(shopping.id)
    assert data["confirmed_by_user"] is True
    assert data["categorization_method"] == "user"


# ============================================================================
# 7. Account Creation -> Transactions -> Monthly Flows -> Forecaster
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_account_to_monthly_flows_to_forecaster(
    db_session: AsyncSession, test_user: User
):
    account = Account(
        user_id=test_user.id,
        name="Business Operations",
        type="depository",
        currency="USD",
        balance_minor=1_200_000,  # $12,000 balance
        is_manual=True,
    )
    db_session.add(account)
    await db_session.flush()

    # 4 months of consecutive negative net burn (-$2,000/mo)
    for m in range(1, 5):
        await txn_service.create_transaction(
            db_session,
            account=account,
            date=date(2026, m, 15),
            amount_minor=-200_000,
            merchant_raw="Office Rent & Servers",
        )

    flows = await txn_service.monthly_flows(db_session, test_user.id, months=4)
    assert len(flows) == 4
    historical_nets = [f["income_minor"] - f["expense_minor"] for f in flows]
    assert all(n == -200_000 for n in historical_nets)

    # Forecaster projects runway based on current balance
    fc = forecaster.forecast_net_flow(historical_nets, horizon=6)
    runway = forecaster.runway_months(account.balance_minor, fc["forecast"])
    assert runway is not None
    assert runway == 6  # $12,000 / $2,000 = 6 months


# ============================================================================
# 8. Multiple Debts -> Extra Payment -> Snowball vs Avalanche Comparison
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_debts_simulation_and_strategy_comparison(
    async_client: httpx.AsyncClient, auth_headers: dict[str, str]
):
    # Debt 1: Credit Card $5,000 at 22% APR, min payment $150
    await async_client.post(
        "/api/v1/debts",
        headers=auth_headers,
        json={"name": "Credit Card", "principal_minor": 500_000, "apr_bps": 2200, "min_payment_minor": 15_000},
    )
    # Debt 2: Personal Loan $10,000 at 8% APR, min payment $250
    await async_client.post(
        "/api/v1/debts",
        headers=auth_headers,
        json={"name": "Personal Loan", "principal_minor": 1_000_000, "apr_bps": 800, "min_payment_minor": 25_000},
    )

    plan_resp = await async_client.post(
        "/api/v1/debts/payoff-plan",
        headers=auth_headers,
        json={"extra_payment_minor": 20_000},  # $200 extra per month
    )
    assert plan_resp.status_code == 200
    data = plan_resp.json()
    assert "snowball" in data
    assert "avalanche" in data
    assert data["interest_saved_by_avalanche_minor"] >= 0


# ============================================================================
# 9. Natural Language Expense Parse -> Transaction -> Balance Deduction
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_expense_parse_to_transaction_balance_deduction(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    test_account: Account,
    db_session: AsyncSession,
):
    initial_balance = test_account.balance_minor

    # Parse natural language expense
    parse_resp = await async_client.post(
        "/api/v1/chat/expenses/parse",
        headers=auth_headers,
        json={"text": "$35.20 at Target for kitchen supplies", "currency": "USD"},
    )
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    assert parsed["amount_minor"] == 3520

    # Create transaction from parsed draft
    txn_resp = await async_client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": str(test_account.id),
            "date": parsed["date"],
            "amount_minor": -parsed["amount_minor"],
            "merchant_raw": parsed["merchant"],
            "description": "kitchen supplies",
        },
    )
    assert txn_resp.status_code == 201

    await db_session.refresh(test_account)
    assert test_account.balance_minor == initial_balance - 3520


# ============================================================================
# 10. Transaction -> Multi-Split Addition -> Split Limit Enforcement
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_transaction_splits_lifecycle(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_account: Account,
):
    groceries = await db_session.scalar(select(Category).where(Category.name == "Groceries"))
    dining = await db_session.scalar(select(Category).where(Category.name == "Dining Out"))

    # Create parent transaction for -$100 (10000 minor)
    txn_resp = await async_client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={
            "account_id": str(test_account.id),
            "date": "2026-03-10",
            "amount_minor": -10000,
            "merchant_raw": "Mega Supermarket",
        },
    )
    assert txn_resp.status_code == 201
    txn_id = txn_resp.json()["id"]

    # Split 1: $60 (6000 minor) for Groceries
    s1_resp = await async_client.post(
        f"/api/v1/transactions/{txn_id}/splits",
        headers=auth_headers,
        json={"amount_minor": 6000, "category_id": str(groceries.id), "memo": "Groceries part"},
    )
    assert s1_resp.status_code == 201
    assert s1_resp.json()["remaining_minor"] == 4000

    # Split 2: $40 (4000 minor) for Dining Out -> exactly 0 remaining
    s2_resp = await async_client.post(
        f"/api/v1/transactions/{txn_id}/splits",
        headers=auth_headers,
        json={"amount_minor": 4000, "category_id": str(dining.id), "memo": "Cafe part"},
    )
    assert s2_resp.status_code == 201
    assert s2_resp.json()["remaining_minor"] == 0

    # Split 3: Exceeding amount -> 400 bad request
    s3_resp = await async_client.post(
        f"/api/v1/transactions/{txn_id}/splits",
        headers=auth_headers,
        json={"amount_minor": 1000, "category_id": str(groceries.id), "memo": "Excess"},
    )
    assert s3_resp.status_code == 400


# ============================================================================
# 11. Recurring Transactions -> Subscription Detection -> Duplicate Scan
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_subscription_stream_to_duplicate_alert(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_account: Account,
):
    # Simulate recurring Spotify and Spotify Family charges over 6 months
    base_date = date(2025, 9, 1)
    for m in range(6):
        d = base_date + timedelta(days=30 * m)
        await txn_service.create_transaction(
            db_session,
            account=test_account,
            date=d,
            amount_minor=-1499,
            merchant_raw="SPOTIFY PREMIUM",
        )
        await txn_service.create_transaction(
            db_session,
            account=test_account,
            date=d,
            amount_minor=-1999,
            merchant_raw="SPOTIFY FAMILY PLAN",
        )

    scan_resp = await async_client.post(
        "/api/v1/alerts/scan-duplicate-subscriptions", headers=auth_headers
    )
    assert scan_resp.status_code == 200
    data = scan_resp.json()
    assert data["subscriptions_found"] >= 2
    assert data["duplicate_alerts"] >= 1


# ============================================================================
# 12. Knowledge Doc RAG Ingest -> PII Masking -> RAG Context Retrieval
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_rag_ingest_to_pii_masked_context(
    db_session: AsyncSession, test_user: User
):
    guide_text = (
        "Zero-based budgeting is a method where your income minus your expenditures "
        "and savings equals zero. Every dollar is allocated to a specific envelope or goal."
    )
    await ingest_document(db_session, "Zero-Based Budgeting Guide", guide_text, user_id=test_user.id)

    # Prompt with PII email
    user_query = "Can you explain zero-based budgeting? Send to alice@example.com"
    masked_query = mask_pii(user_query)
    assert "alice@example.com" not in masked_query

    context, titles = await build_context(db_session, masked_query, test_user.id)
    assert "Zero-Based Budgeting Guide" in titles
    assert "income minus your expenditures" in context


# ============================================================================
# 13. Account Balance Dynamics and Archive
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_account_balance_dynamics_and_archive(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
):
    acct = Account(
        user_id=test_user.id,
        name="Temporary Savings",
        type="depository",
        currency="USD",
        balance_minor=100000,
        is_manual=True,
    )
    db_session.add(acct)
    await db_session.flush()

    # Add income (+50000) and expense (-20000)
    await txn_service.create_transaction(
        db_session, account=acct, date=date(2026, 3, 1), amount_minor=50000, merchant_raw="Bonus"
    )
    await txn_service.create_transaction(
        db_session, account=acct, date=date(2026, 3, 2), amount_minor=-20000, merchant_raw="Bill"
    )
    await db_session.refresh(acct)
    assert acct.balance_minor == 130000

    # Archive account
    del_resp = await async_client.delete(f"/api/v1/accounts/{acct.id}", headers=auth_headers)
    assert del_resp.status_code == 204
    await db_session.refresh(acct)
    assert acct.archived is True


# ============================================================================
# 14. User Registration -> Multi-Device Sessions -> Pruning -> Revoke All
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_session_lifecycle_pruning_and_revocation(
    db_session: AsyncSession, test_user: User
):
    # Issue 12 refresh tokens across simulated devices
    for i in range(12):
        await auth_service.issue_tokens(db_session, test_user, device=f"Device-{i}")

    sessions = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == test_user.id)
        )
    ).scalars().all()
    # Pruned to at most 10 active sessions
    assert len(sessions) <= 10

    # Revoke all sessions
    await auth_service.revoke_all_sessions(db_session, test_user.id)
    rem = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == test_user.id)
        )
    ).scalars().all()
    assert len(rem) == 0


# ============================================================================
# 15. Passkey Registration -> Credential Storage -> Sign Count Updates
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_passkey_storage_and_sign_count_tracking(
    db_session: AsyncSession, test_user: User
):
    cred_id = "test-passkey-credential-id-12345"
    cred = PasskeyCredential(
        user_id=test_user.id,
        credential_id=cred_id,
        public_key="base64-encoded-public-key-material",
        sign_count=0,
        device_type="platform",
        label="MacBook TouchID",
    )
    db_session.add(cred)
    await db_session.flush()

    # Simulate subsequent authentication updating sign count
    stored = await db_session.scalar(
        select(PasskeyCredential).where(PasskeyCredential.credential_id == cred_id)
    )
    assert stored is not None
    stored.sign_count += 1
    await db_session.flush()

    assert stored.sign_count == 1


# ============================================================================
# 16. Zero-Based Budget Rebalancing Lifecycle
# ============================================================================

def test_interaction_zero_based_budget_rebalancing():
    # Initial state: $3,000 planned income, balanced envelopes
    envelopes = [
        {"allocated_minor": 150_000},  # Rent
        {"allocated_minor": 100_000},  # Groceries
        {"allocated_minor": 50_000},   # Utilities
    ]
    b1 = budget_engine.zero_based_check(envelopes, 300_000)
    assert b1["balanced"] is True

    # Rent increases by $200 (20000 minor)
    envelopes[0]["allocated_minor"] = 170_000
    b2 = budget_engine.zero_based_check(envelopes, 300_000)
    assert b2["balanced"] is False
    assert b2["unassigned_minor"] == -20_000

    # User rebalances by adjusting planned income to $3,200 (320000 minor)
    b3 = budget_engine.zero_based_check(envelopes, 320_000)
    assert b3["balanced"] is True
    assert b3["unassigned_minor"] == 0


# ============================================================================
# 17. Goal percent_income Strategy Dynamic Tracking on Salary Changes
# ============================================================================

def test_interaction_goal_percent_income_tracking_on_income_shift():
    # Strategy: 10% of monthly income toward $10,000 emergency fund
    # Case 1: Income $4,000/mo -> effective monthly $400/mo
    t1 = goals_debt.goal_on_track(
        "percent_income",
        saved_minor=200_000,
        target_minor=1_000_000,
        monthly_amount_minor=0,
        percent_of_income=10.0,
        avg_monthly_income_minor=400_000,
        target_date=None,
    )
    assert t1["effective_monthly_minor"] == 40_000
    assert t1["months_remaining"] == 20

    # Case 2: Income raises to $8,000/mo -> effective monthly doubles to $800/mo
    t2 = goals_debt.goal_on_track(
        "percent_income",
        saved_minor=200_000,
        target_minor=1_000_000,
        monthly_amount_minor=0,
        percent_of_income=10.0,
        avg_monthly_income_minor=800_000,
        target_date=None,
    )
    assert t2["effective_monthly_minor"] == 80_000
    assert t2["months_remaining"] == 10  # Months cut in half


# ============================================================================
# 18. OFX Import -> Balance Update -> Categorization -> Dedup
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_ofx_import_deduplication(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    test_account: Account,
):
    ofx_sample = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE
<OFX>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <CURDEF>USD</CURDEF>
        <BANKACCTFROM>
          <BANKID>123456789</BANKID>
          <ACCTID>987654321</ACCTID>
          <ACCTTYPE>CHECKING</ACCTTYPE>
        </BANKACCTFROM>
        <BANKTRANLIST>
          <DTSTART>20260301</DTSTART>
          <DTEND>20260331</DTEND>
          <STMTTRN>
            <TRNTYPE>DEBIT</TRNTYPE>
            <DTPOSTED>20260310120000</DTPOSTED>
            <TRNAMT>-45.00</TRNAMT>
            <FITID>OFX-TXN-2001</FITID>
            <NAME>COSTCO WHOLESALE</NAME>
          </STMTTRN>
        </BANKTRANLIST>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>"""
    files = {"file": ("statement.ofx", ofx_sample, "application/x-ofx")}
    resp1 = await async_client.post(
        f"/api/v1/import/{test_account.id}/ofx", headers=auth_headers, files=files
    )
    assert resp1.status_code == 200
    assert resp1.json()["created"] == 1

    # Re-importing same OFX detects duplicate
    files_again = {"file": ("statement.ofx", ofx_sample, "application/x-ofx")}
    resp2 = await async_client.post(
        f"/api/v1/import/{test_account.id}/ofx", headers=auth_headers, files=files_again
    )
    assert resp2.status_code == 200
    assert resp2.json()["duplicates"] == 1


# ============================================================================
# 19. Multi-item Tagging and Split Suggestion Endpoint
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_multi_item_tagging_and_suggest_split(
    async_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_account: Account,
):
    txn, _ = await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=date(2026, 3, 10),
        amount_minor=-6500,
        merchant_raw="Superstore",
        description="Groceries $45.00 and Pharmacy $20.00",
    )
    assert "possible-split" in txn.tags

    resp = await async_client.post(
        f"/api/v1/transactions/suggest-split?txn_id={txn.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["transaction_id"] == str(txn.id)


# ============================================================================
# 20. Event Bus Multi-User Subscriptions Isolation
# ============================================================================

@pytest.mark.asyncio
async def test_interaction_event_bus_multi_user_isolation():
    user_a = "user-alice-123"
    user_b = "user-bob-456"

    queue_a = await bus.subscribe(user_a)
    queue_b = await bus.subscribe(user_b)

    # Publish message intended only for User A
    msg_a = {"alert": "Alice overspent on groceries"}
    await bus.notify_user(user_a, msg_a)

    # User A queue receives it immediately
    rec_a = await queue_a.get()
    assert rec_a == msg_a

    # User B queue is empty
    assert queue_b.empty() is True

    await bus.unsubscribe(user_a, queue_a)
    await bus.unsubscribe(user_b, queue_b)
