"""Empirical Stress Test Suite for Milestone M2.

Focus Areas:
1. Stripe Provider (balance parsing, multi-currency handling, transaction mapping, webhook event processing, token hashing).
2. Australian Bank Registry & Regional Categorization (/api/v1/connections/providers with AU, US, EU, Business, GLOBAL).
3. Family / Multi-Profile Lifecycle & Permissions (create, invite, role hierarchy, child spending limit mutations, monthly spend aggregation).
4. AI Eval History Router (pagination math, limit boundaries, user isolation, sorting, telemetry fields).
"""
from __future__ import annotations

import datetime
from datetime import UTC, date, datetime, timedelta
import os
import sys
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add server directory to sys.path
server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from app.core.crypto import seal
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import (
    Account,
    AiEvalLog,
    BankConnection,
    Category,
    FamilyGroup,
    FamilyMember,
    FamilyRole,
    Transaction,
    User,
)
from app.services.providers import (
    AustralianBankProvider,
    BaseProvider,
    BasiqProvider,
    GoCardlessProvider,
    MockBankProvider,
    PlaidProvider,
    ProviderAccount,
    ProviderTxn,
    StripeProvider,
    available_providers,
    get_providers,
)


# Helper to build headers for any user
def make_auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, {"email": user.email})
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. STRIPE PROVIDER EMPIRICAL STRESS TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stripe_provider_exchange_determinism_and_hashing():
    """Verify Stripe exchange produces deterministic external ID format."""
    p1 = StripeProvider(api_key="sk_live_test_key_123")
    p2 = StripeProvider(api_key="sk_live_test_key_123")
    
    ext_id_1 = await p1.exchange("sk_live_test_key_123")
    ext_id_2 = await p2.exchange("sk_live_test_key_123")
    
    assert ext_id_1 == ext_id_2
    assert ext_id_1.startswith("acct_stripe_")
    assert len(ext_id_1) == len("acct_stripe_") + 12
    assert p1.last_access_token == "sk_live_test_key_123"

    # Different key produces different hash
    ext_id_3 = await p1.exchange("sk_live_different_key_456")
    assert ext_id_3 != ext_id_1
    assert ext_id_3.startswith("acct_stripe_")


@pytest.mark.asyncio
async def test_stripe_provider_create_link_structure():
    """Verify Stripe link initiation contains required redirect structure."""
    p = StripeProvider()
    link_info = await p.create_link("user-test-uuid-99", None)
    assert link_info["provider"] == "stripe"
    assert link_info["status"] == "ready"
    assert "state=user-test-uuid-99" in link_info["link_url"]
    assert "https://dashboard.stripe.com/oauth/authorize" in link_info["link_url"]


@pytest.mark.asyncio
async def test_stripe_provider_fallback_accounts_and_transactions():
    """Verify fallback behavior for mock Stripe keys."""
    p = StripeProvider(api_key="sk_test_mock_12345")
    mock_conn = BankConnection(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider="stripe",
        region="Business",
        external_id="acct_stripe_mock123",
        access_token_sealed=seal("sk_test_mock_12345"),
    )
    
    # Accounts
    accounts = await p.fetch_accounts(mock_conn)
    assert len(accounts) == 1
    acct = accounts[0]
    assert acct.external_id == f"{mock_conn.external_id}_bal"
    assert acct.name == "Stripe Business Balance"
    assert acct.type == "depository"
    assert acct.subtype == "business"
    assert acct.currency == "AUD"
    assert acct.balance_minor == 1452000

    # Transactions
    txns_map = await p.fetch_transactions(mock_conn, days=30)
    assert acct.external_id in txns_map
    txns = txns_map[acct.external_id]
    assert len(txns) == 3
    assert all(isinstance(t, ProviderTxn) for t in txns)
    assert txns[0].amount_minor == 49900
    assert txns[1].amount_minor == 125000
    assert txns[2].amount_minor == 75000
    assert txns[0].merchant_raw == "Acme Client Pty Ltd"


@pytest.mark.asyncio
async def test_stripe_webhook_handler_payload_variations():
    """Stress test handle_webhook across valid, edge-case, and empty payloads."""
    p = StripeProvider()

    # 1. Standard charge.succeeded
    payload1 = {
        "id": "evt_111",
        "type": "charge.succeeded",
        "data": {
            "object": {
                "id": "ch_111",
                "amount": 25000,
                "currency": "usd",
                "description": "Custom Software Dev",
                "customer": "cus_999",
            }
        }
    }
    res1 = await p.handle_webhook(payload1)
    assert res1["processed"] is True
    assert res1["event_id"] == "evt_111"
    assert res1["event_type"] == "charge.succeeded"
    assert res1["amount_minor"] == 25000
    assert res1["currency"] == "USD"
    assert res1["description"] == "Custom Software Dev"
    assert res1["customer"] == "cus_999"

    # 2. Empty payload (graceful degradation)
    res2 = await p.handle_webhook({})
    assert res2["processed"] is True
    assert res2["event_type"] == ""
    assert res2["amount_minor"] == 0
    assert res2["currency"] == "AUD"

    # 3. Missing data object
    res3 = await p.handle_webhook({"id": "evt_no_data", "type": "payment_intent.created"})
    assert res3["processed"] is True
    assert res3["event_id"] == "evt_no_data"
    assert res3["event_type"] == "payment_intent.created"


@pytest.mark.asyncio
async def test_stripe_connect_and_duplicate_connect_upsert(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Verify POST /api/v1/connections/stripe/connect handles new connection and re-connection updates cleanly."""
    # First connect
    res1 = await async_client.post(
        "/api/v1/connections/stripe/connect",
        json={"api_key": "sk_test_first_key_111"},
        headers=auth_headers,
    )
    assert res1.status_code == 201
    d1 = res1.json()
    conn_id_1 = d1["connection_id"]
    assert d1["status"] == "connected"
    assert d1["provider"] == "stripe"
    assert d1["region"] == "Business"

    # Verify Account created in DB
    acct = await db_session.scalar(
        select(Account).where(Account.user_id == test_user.id, Account.connection_id == uuid.UUID(conn_id_1))
    )
    assert acct is not None
    assert acct.name == "Stripe Business Account"
    assert acct.subtype == "business"
    assert acct.currency == "AUD"
    assert acct.balance_minor == 1452000

    # Re-connect with updated key (upsert scenario)
    res2 = await async_client.post(
        "/api/v1/connections/stripe/connect",
        json={"api_key": "sk_test_second_key_222"},
        headers=auth_headers,
    )
    assert res2.status_code == 201
    d2 = res2.json()
    assert d2["connection_id"] == conn_id_1  # Reuses existing connection ID

    # Verify list connections endpoint shows single Stripe connection
    list_res = await async_client.get("/api/v1/connections", headers=auth_headers)
    assert list_res.status_code == 200
    stripe_conns = [c for c in list_res.json() if c["provider"] == "stripe"]
    assert len(stripe_conns) == 1
    assert stripe_conns[0]["region"] == "Business"


@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_creates_real_transaction(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Verify POST /api/v1/connections/stripe/webhook ingests transaction for connected user."""
    # 1. Connect Stripe first
    await async_client.post(
        "/api/v1/connections/stripe/connect",
        json={"api_key": "sk_test_key_for_webhook"},
        headers=auth_headers,
    )

    # 2. Fire webhook
    unique_charge_id = f"ch_stress_{uuid.uuid4().hex[:8]}"
    wh_payload = {
        "id": f"evt_{uuid.uuid4().hex[:8]}",
        "type": "charge.succeeded",
        "data": {
            "object": {
                "id": unique_charge_id,
                "amount": 189500,
                "currency": "aud",
                "description": "Enterprise Retainer Payment",
                "billing_details": {"name": "MegaCorp Australia"},
            }
        }
    }
    wh_resp = await async_client.post(
        "/api/v1/connections/stripe/webhook",
        json=wh_payload,
        headers={"Stripe-Signature": "t=12345,v1=signature_hash"},
    )
    assert wh_resp.status_code == 200
    assert wh_resp.json()["received"] is True
    assert wh_resp.json()["status"] == "processed"

    # 3. Verify Transaction created in DB
    txn = await db_session.scalar(
        select(Transaction).where(Transaction.external_id == unique_charge_id)
    )
    assert txn is not None
    assert txn.amount_minor == 189500
    assert txn.merchant_raw == "MegaCorp Australia"
    assert txn.description == "Enterprise Retainer Payment"
    assert txn.currency == "AUD"


# ─────────────────────────────────────────────────────────────────────────────
# 2. AUSTRALIAN BANK REGISTRY & REGIONAL CATEGORIZATION
# ─────────────────────────────────────────────────────────────────────────────

def test_all_10_australian_banks_registered_and_configured():
    """Verify all 10 major Australian banks exist in registry with correct region & Basiq configuration."""
    providers = get_providers()
    
    expected_banks = {
        "cba": "Commonwealth Bank",
        "westpac": "Westpac",
        "anz": "ANZ Bank",
        "nab": "National Australia Bank",
        "macquarie": "Macquarie Bank",
        "suncorp": "Suncorp Bank",
        "bendigo": "Bendigo Bank",
        "boq": "Bank of Queensland",
        "ing_au": "ING Australia",
        "up": "UP Bank",
    }

    for key, name in expected_banks.items():
        assert key in providers, f"Missing bank in registry: {key}"
        prov = providers[key]
        assert isinstance(prov, AustralianBankProvider)
        assert prov.region == "AU"
        assert prov.name == name
        assert prov.institution_code == key
        assert prov.is_configured() is True


def test_regional_providers_categorization_and_metadata():
    """Test available_providers() metadata structure and grouping."""
    provs = available_providers()
    assert len(provs) >= 16

    keys = {p["key"] for p in provs}
    assert "plaid" in keys
    assert "gocardless" in keys
    assert "basiq" in keys
    assert "stripe" in keys
    assert "cba" in keys
    assert "mock" in keys

    for p in provs:
        assert "key" in p
        assert "name" in p
        assert "region" in p
        assert "configured" in p
        assert isinstance(p["configured"], bool)


@pytest.mark.asyncio
async def test_get_providers_endpoint_regional_breakdown(async_client: AsyncClient):
    """Test GET /api/v1/connections/providers returns by_region mapping with AU, US, EU, Business, GLOBAL."""
    resp = await async_client.get("/api/v1/connections/providers")
    assert resp.status_code == 200
    data = resp.json()

    assert "providers" in data
    assert "by_region" in data
    by_region = data["by_region"]

    assert "AU" in by_region
    assert "US" in by_region
    assert "EU" in by_region
    assert "Business" in by_region
    assert "GLOBAL" in by_region

    # Check AU contains all 10 banks + basiq
    au_keys = {p["key"] for p in by_region["AU"]}
    assert "basiq" in au_keys
    assert "cba" in au_keys
    assert "westpac" in au_keys
    assert "anz" in au_keys
    assert "nab" in au_keys
    assert "macquarie" in au_keys
    assert "up" in au_keys
    assert len(au_keys) == 11

    # Check Business contains Stripe
    biz_keys = {p["key"] for p in by_region["Business"]}
    assert "stripe" in biz_keys

    # Check US contains Plaid
    us_keys = {p["key"] for p in by_region["US"]}
    assert "plaid" in us_keys

    # Check EU contains GoCardless
    eu_keys = {p["key"] for p in by_region["EU"]}
    assert "gocardless" in eu_keys


@pytest.mark.asyncio
async def test_link_start_invalid_provider_returns_404(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test /api/v1/connections/link/start with non-existent provider returns 404."""
    resp = await async_client.post(
        "/api/v1/connections/link/start",
        json={"provider": "invalid_fake_provider"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert "Unknown provider" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. FAMILY / MULTI-PROFILE LIFECYCLE & SPENDING LIMIT MUTATIONS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_family_group_creation_and_owner_assignment(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
):
    """Test family creation sets creator as OWNER."""
    resp = await async_client.post(
        "/api/v1/family",
        json={"name": "The Henderson Family"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "The Henderson Family"
    assert data["owner_id"] == str(test_user.id)
    assert len(data["members"]) == 1
    assert data["members"][0]["role"] == "owner"
    assert data["members"][0]["user_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_family_multi_role_invites_and_spending_limits(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test full invite lifecycle: admin, member, child with spending limit, and duplicate handling."""
    # 1. Create family
    fam_resp = await async_client.post(
        "/api/v1/family",
        json={"name": "Johnson Household"},
        headers=auth_headers,
    )
    assert fam_resp.status_code == 201

    # 2. Invite spouse as ADMIN
    spouse_resp = await async_client.post(
        "/api/v1/family/members/invite",
        json={"email": "spouse@example.com", "role": "admin"},
        headers=auth_headers,
    )
    assert spouse_resp.status_code == 201
    spouse_data = spouse_resp.json()
    assert spouse_data["role"] == "admin"
    assert spouse_data["email"] == "spouse@example.com"
    assert spouse_data["spending_limit_minor"] is None

    # 3. Invite teenager as CHILD with spending limit 15000 ($150.00)
    child_resp = await async_client.post(
        "/api/v1/family/members/invite",
        json={
            "email": "teen@example.com",
            "role": "child",
            "spending_limit_minor": 15000,
        },
        headers=auth_headers,
    )
    assert child_resp.status_code == 201
    child_data = child_resp.json()
    assert child_data["role"] == "child"
    assert child_data["spending_limit_minor"] == 15000
    child_id = child_data["id"]

    # 4. Duplicate invite to active member returns 400 Bad Request
    dup_resp = await async_client.post(
        "/api/v1/family/members/invite",
        json={"email": "teen@example.com", "role": "child"},
        headers=auth_headers,
    )
    assert dup_resp.status_code == 400
    assert "already a member" in dup_resp.json()["detail"]

    # 5. Patch child spending limit (increase to 25000)
    patch_limit_resp = await async_client.patch(
        f"/api/v1/family/members/{child_id}",
        json={"spending_limit_minor": 25000},
        headers=auth_headers,
    )
    assert patch_limit_resp.status_code == 200
    assert patch_limit_resp.json()["spending_limit_minor"] == 25000
    assert patch_limit_resp.json()["role"] == "child"

    # 6. Patch child to remove limit (set to None) and upgrade to MEMBER
    patch_role_resp = await async_client.patch(
        f"/api/v1/family/members/{child_id}",
        json={"role": "member", "spending_limit_minor": None},
        headers=auth_headers,
    )
    assert patch_role_resp.status_code == 200
    assert patch_role_resp.json()["role"] == "member"

    # 7. Check overview endpoint reflects all members
    overview_resp = await async_client.get("/api/v1/family/overview", headers=auth_headers)
    assert overview_resp.status_code == 200
    overview = overview_resp.json()
    assert len(overview["members"]) == 3
    roles = {m["role"] for m in overview["members"]}
    assert roles == {"owner", "admin", "member"}


@pytest.mark.asyncio
async def test_family_permissions_enforcement(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Adversarial test: Non-owner / non-admin cannot invite or modify family members."""
    # 1. Create owner and member users
    owner_user = User(email=f"owner_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    regular_user = User(email=f"member_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    db_session.add_all([owner_user, regular_user])
    await db_session.flush()

    owner_headers = make_auth_headers(owner_user)
    member_headers = make_auth_headers(regular_user)

    # 2. Owner creates family
    fam_resp = await async_client.post(
        "/api/v1/family",
        json={"name": "Protected Household"},
        headers=owner_headers,
    )
    assert fam_resp.status_code == 201

    # 3. Owner invites regular_user as regular MEMBER
    inv_resp = await async_client.post(
        "/api/v1/family/members/invite",
        json={"email": regular_user.email, "role": "member"},
        headers=owner_headers,
    )
    assert inv_resp.status_code == 201
    member_member_id = inv_resp.json()["id"]

    # 4. Regular member attempts to invite someone -> MUST FAIL 403 Forbidden
    unauth_inv = await async_client.post(
        "/api/v1/family/members/invite",
        json={"email": "attacker@example.com", "role": "admin"},
        headers=member_headers,
    )
    assert unauth_inv.status_code == 403
    assert "Only family owners and administrators" in unauth_inv.json()["detail"]

    # 5. Regular member attempts to patch member -> MUST FAIL 403 Forbidden
    unauth_patch = await async_client.patch(
        f"/api/v1/family/members/{member_member_id}",
        json={"role": "admin"},
        headers=member_headers,
    )
    assert unauth_patch.status_code == 403

    # 6. Regular member attempts to delete another member -> MUST FAIL 403 Forbidden
    owner_m_id = fam_resp.json()["members"][0]["id"]
    unauth_del = await async_client.delete(
        f"/api/v1/family/members/{owner_m_id}",
        headers=member_headers,
    )
    assert unauth_del.status_code == 403

    # 7. Member CAN delete / leave themselves (self-removal) -> MUST SUCCEED 204
    self_del = await async_client.delete(
        f"/api/v1/family/members/{member_member_id}",
        headers=member_headers,
    )
    assert self_del.status_code == 204


@pytest.mark.asyncio
async def test_family_monthly_spend_aggregation_calculation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify family overview computes accurate monthly spending per member and total household spend."""
    # 1. Create owner and child users
    owner = User(email=f"mom_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    child = User(email=f"kid_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    db_session.add_all([owner, child])
    await db_session.flush()

    mom_headers = make_auth_headers(owner)

    # 2. Mom creates family & invites kid
    await async_client.post("/api/v1/family", json={"name": "Spending Household"}, headers=mom_headers)
    await async_client.post(
        "/api/v1/family/members/invite",
        json={"email": child.email, "role": "child", "spending_limit_minor": 10000},
        headers=mom_headers,
    )

    # 3. Create accounts & transactions in current calendar month
    today = date.today()
    start_of_month = date(today.year, today.month, 1)

    mom_acct = Account(user_id=owner.id, name="Mom Checking", type="depository", currency="AUD", balance_minor=500000)
    kid_acct = Account(user_id=child.id, name="Kid Debit", type="depository", currency="AUD", balance_minor=5000)
    db_session.add_all([mom_acct, kid_acct])
    await db_session.flush()

    # Mom spent: $120.50 groceries (expense), $2000 salary (income, excluded from spend)
    t1 = Transaction(
        user_id=owner.id, account_id=mom_acct.id, date=start_of_month,
        amount_minor=-12050, currency="AUD", merchant_raw="Woolworths", is_income=False, excluded=False
    )
    t2 = Transaction(
        user_id=owner.id, account_id=mom_acct.id, date=start_of_month,
        amount_minor=200000, currency="AUD", merchant_raw="Salary", is_income=True, excluded=False
    )
    # Kid spent: $35.00 games (expense), $15.00 refund/excluded
    t3 = Transaction(
        user_id=child.id, account_id=kid_acct.id, date=start_of_month,
        amount_minor=-3500, currency="AUD", merchant_raw="Steam Games", is_income=False, excluded=False
    )
    t4 = Transaction(
        user_id=child.id, account_id=kid_acct.id, date=start_of_month,
        amount_minor=-1500, currency="AUD", merchant_raw="Excluded Txn", is_income=False, excluded=True
    )
    db_session.add_all([t1, t2, t3, t4])
    await db_session.commit()

    # 4. Fetch Overview
    res = await async_client.get("/api/v1/family/overview", headers=mom_headers)
    assert res.status_code == 200
    ov = res.json()

    # Expected: Mom spent 12050, Kid spent 3500, Total = 15550
    assert ov["total_spent_minor"] == 15550
    member_spends = {m["email"]: m["spent_this_month_minor"] for m in ov["members"]}
    assert member_spends[owner.email] == 12050
    assert member_spends[child.email] == 3500


# ─────────────────────────────────────────────────────────────────────────────
# 4. AI EVAL HISTORY ENDPOINT PAGINATION, FILTERING & ISOLATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_eval_history_pagination_and_sorting(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Stress test AI eval history endpoint pagination math, limit boundaries, and desc ordering."""
    base_time = datetime.now(UTC)

    # Insert 15 eval logs with varying timestamps
    logs = []
    for i in range(15):
        logs.append(
            AiEvalLog(
                user_id=test_user.id,
                thread_id=uuid.uuid4(),
                message_id=uuid.uuid4(),
                provider_used="mock_openai" if i % 2 == 0 else "mock_anthropic",
                model_name="gpt-4o-mini" if i % 2 == 0 else "claude-3-5-haiku",
                tokens_in=100 + i * 10,
                tokens_out=200 + i * 20,
                latency_ms=150 + i * 5,
                route_chosen="coach" if i % 3 == 0 else ("tax" if i % 3 == 1 else "audit"),
                confidence_score=round(0.80 + (i * 0.01), 2),
                pii_fields_masked=i % 2,
                query_summary=f"Stress query {i:02d}",
                created_at=base_time + timedelta(minutes=i),
            )
        )
    db_session.add_all(logs)
    await db_session.commit()

    # Page 1, limit 5 (should return newest 5: indices 14, 13, 12, 11, 10)
    p1_res = await async_client.get("/api/v1/ai/eval/history?page=1&limit=5", headers=auth_headers)
    assert p1_res.status_code == 200
    p1 = p1_res.json()
    assert p1["page"] == 1
    assert p1["limit"] == 5
    assert p1["total"] >= 15
    assert len(p1["items"]) == 5
    assert p1["items"][0]["query_summary"] == "Stress query 14"
    assert p1["items"][4]["query_summary"] == "Stress query 10"

    # Page 2, limit 5 (should return next 5: indices 9, 8, 7, 6, 5)
    p2_res = await async_client.get("/api/v1/ai/eval/history?page=2&limit=5", headers=auth_headers)
    assert p2_res.status_code == 200
    p2 = p2_res.json()
    assert p2["page"] == 2
    assert len(p2["items"]) == 5
    assert p2["items"][0]["query_summary"] == "Stress query 09"
    assert p2["items"][4]["query_summary"] == "Stress query 05"

    # Out of range page (page 50 with limit 5)
    p_empty_res = await async_client.get("/api/v1/ai/eval/history?page=50&limit=5", headers=auth_headers)
    assert p_empty_res.status_code == 200
    p_empty = p_empty_res.json()
    assert p_empty["page"] == 50
    assert len(p_empty["items"]) == 0
    assert p_empty["total"] >= 15


@pytest.mark.asyncio
async def test_ai_eval_history_query_param_validation(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """Test validation boundaries: page < 1, limit < 1, limit > 100 return 422."""
    # page = 0
    res1 = await async_client.get("/api/v1/ai/eval/history?page=0&limit=10", headers=auth_headers)
    assert res1.status_code == 422

    # page = -5
    res2 = await async_client.get("/api/v1/ai/eval/history?page=-5&limit=10", headers=auth_headers)
    assert res2.status_code == 422

    # limit = 0
    res3 = await async_client.get("/api/v1/ai/eval/history?page=1&limit=0", headers=auth_headers)
    assert res3.status_code == 422

    # limit = 101 (exceeds max 100)
    res4 = await async_client.get("/api/v1/ai/eval/history?page=1&limit=101", headers=auth_headers)
    assert res4.status_code == 422


@pytest.mark.asyncio
async def test_ai_eval_history_multi_user_data_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Adversarial data leakage test: User A must never see User B's AI eval history logs."""
    user_a = User(email=f"alice_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    user_b = User(email=f"bob_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    # User A log
    log_a = AiEvalLog(
        user_id=user_a.id,
        provider_used="mock_openai",
        model_name="gpt-4o",
        tokens_in=50,
        tokens_out=50,
        latency_ms=100,
        route_chosen="coach",
        confidence_score=0.99,
        pii_fields_masked=0,
        query_summary="Alice Secret Budgeting Query",
    )
    # User B log
    log_b = AiEvalLog(
        user_id=user_b.id,
        provider_used="mock_anthropic",
        model_name="claude-3-5",
        tokens_in=80,
        tokens_out=80,
        latency_ms=200,
        route_chosen="tax",
        confidence_score=0.95,
        pii_fields_masked=2,
        query_summary="Bob Secret Tax Evasion Query",
    )
    db_session.add_all([log_a, log_b])
    await db_session.commit()

    headers_a = make_auth_headers(user_a)
    headers_b = make_auth_headers(user_b)

    # Query as Alice
    res_a = await async_client.get("/api/v1/ai/eval/history", headers=headers_a)
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["total"] == 1
    assert data_a["items"][0]["query_summary"] == "Alice Secret Budgeting Query"
    assert data_a["items"][0]["user_id"] == str(user_a.id)

    # Query as Bob
    res_b = await async_client.get("/api/v1/ai/eval/history", headers=headers_b)
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["total"] == 1
    assert data_b["items"][0]["query_summary"] == "Bob Secret Tax Evasion Query"
    assert data_b["items"][0]["user_id"] == str(user_b.id)


# ─────────────────────────────────────────────────────────────────────────────
# 5. ADDITIONAL ADVERSARIAL STRESS & CONTRACT TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stripe_full_sync_and_deduplication(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test sync_connection on Stripe provider and idempotency/deduplication on repeated syncs."""
    from app.services.providers import sync_connection

    # 1. Connect Stripe
    res = await async_client.post(
        "/api/v1/connections/stripe/connect",
        json={"api_key": "sk_test_sync_test_key"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    conn_id = uuid.UUID(res.json()["connection_id"])
    conn = await db_session.get(BankConnection, conn_id)
    assert conn is not None

    provider = StripeProvider(api_key="sk_test_sync_test_key")

    # 2. First Sync: should create 3 fallback/mock transactions
    sync1 = await sync_connection(db_session, test_user.id, conn, provider)
    assert sync1["created_txns"] == 3
    assert sync1["duplicates"] == 0
    assert len(sync1["errors"]) == 0

    # 3. Second Sync: all 3 should be detected as duplicates
    sync2 = await sync_connection(db_session, test_user.id, conn, provider)
    assert sync2["created_txns"] == 0
    assert sync2["duplicates"] == 3
    assert len(sync2["errors"]) == 0


@pytest.mark.asyncio
async def test_stripe_webhook_unhandled_event_type_and_missing_data(
    async_client: AsyncClient,
):
    """Test Stripe webhook with unexpected event types and null payload data."""
    # 1. Unhandled event type
    res1 = await async_client.post(
        "/api/v1/connections/stripe/webhook",
        json={"id": "evt_sub_001", "type": "customer.subscription.created", "data": {}},
    )
    assert res1.status_code == 200
    assert res1.json()["received"] is True
    assert res1.json()["event"] == "customer.subscription.created"
    assert res1.json()["status"] == "processed"

    # 2. Null/empty data object
    res2 = await async_client.post(
        "/api/v1/connections/stripe/webhook",
        json={"id": "evt_empty", "type": "charge.succeeded", "data": None},
    )
    assert res2.status_code == 200
    assert res2.json()["received"] is True


@pytest.mark.asyncio
async def test_australian_bank_link_complete_and_connection_management(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Test /link/complete for Australian Bank (CBA) and subsequent revoke lifecycle."""
    # 1. Link complete with CBA
    res = await async_client.post(
        "/api/v1/connections/link/complete",
        json={
            "provider": "cba",
            "basiq_user_id": "usr_cba_basiq_9999",
            "institution_name": "Commonwealth Bank of Australia",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "cba"
    conn_id = uuid.UUID(data["connection_id"])

    # 2. Verify connection in list
    list_res = await async_client.get("/api/v1/connections", headers=auth_headers)
    assert list_res.status_code == 200
    conns = list_res.json()
    cba_conn = next(c for c in conns if c["id"] == str(conn_id))
    assert cba_conn["provider"] == "cba"
    assert cba_conn["region"] == "AU"
    assert cba_conn["institution_name"] == "Commonwealth Bank of Australia"

    # 3. Revoke connection
    del_res = await async_client.delete(f"/api/v1/connections/{conn_id}", headers=auth_headers)
    assert del_res.status_code == 204

    # 4. Verify status updated to revoked in DB
    updated_conn = await db_session.get(BankConnection, conn_id)
    assert updated_conn.status == "revoked"


@pytest.mark.asyncio
async def test_family_reinvite_reactivation_and_zero_spending_limit(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Test member deletion and subsequent re-invitation reactivation with $0 limit."""
    owner = User(email=f"parent_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    db_session.add(owner)
    await db_session.flush()
    owner_headers = make_auth_headers(owner)

    # 1. Create family
    await async_client.post("/api/v1/family", json={"name": "Reactivation Family"}, headers=owner_headers)

    # 2. Invite member
    inv1 = await async_client.post(
        "/api/v1/family/members/invite",
        json={"email": "temp_member@example.com", "role": "member", "spending_limit_minor": 5000},
        headers=owner_headers,
    )
    assert inv1.status_code == 201
    member_id = inv1.json()["id"]

    # 3. Member deletes themselves (or is deleted)
    del_res = await async_client.delete(f"/api/v1/family/members/{member_id}", headers=owner_headers)
    assert del_res.status_code == 204

    # 4. Re-invite the same email with role=child and spending_limit_minor=0
    inv2 = await async_client.post(
        "/api/v1/family/members/invite",
        json={"email": "temp_member@example.com", "role": "child", "spending_limit_minor": 0},
        headers=owner_headers,
    )
    assert inv2.status_code == 201
    d2 = inv2.json()
    assert d2["role"] == "child"
    assert d2["spending_limit_minor"] == 0
    assert d2["is_active"] is True


@pytest.mark.asyncio
async def test_family_admin_cannot_demote_or_modify_owner(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Adversarial test: Admin cannot demote owner or delete owner from family."""
    owner = User(email=f"true_owner_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    admin_user = User(email=f"sub_admin_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    db_session.add_all([owner, admin_user])
    await db_session.flush()

    owner_headers = make_auth_headers(owner)
    admin_headers = make_auth_headers(admin_user)

    # 1. Create family and invite admin
    fam_res = await async_client.post("/api/v1/family", json={"name": "Hierarchical Family"}, headers=owner_headers)
    owner_member_id = fam_res.json()["members"][0]["id"]

    await async_client.post(
        "/api/v1/family/members/invite",
        json={"email": admin_user.email, "role": "admin"},
        headers=owner_headers,
    )

    # 2. Admin attempts to patch owner's role to member -> 403 Forbidden
    unauth_patch = await async_client.patch(
        f"/api/v1/family/members/{owner_member_id}",
        json={"role": "member"},
        headers=admin_headers,
    )
    assert unauth_patch.status_code == 403
    assert "Cannot modify family group owner" in unauth_patch.json()["detail"]

    # 3. Admin attempts to delete owner -> 400 Bad Request
    unauth_del = await async_client.delete(
        f"/api/v1/family/members/{owner_member_id}",
        headers=admin_headers,
    )
    assert unauth_del.status_code == 400
    assert "Cannot remove the owner" in unauth_del.json()["detail"]


@pytest.mark.asyncio
async def test_ai_eval_history_null_fields_and_large_scale_pagination(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Stress test AI eval history with 50 logs containing NULL metrics to verify schema defaults & pagination."""
    test_user = User(email=f"eval_stress_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    db_session.add(test_user)
    await db_session.flush()
    headers = make_auth_headers(test_user)

    base_time = datetime.now(UTC)

    # 50 records with NULL metrics
    bulk_logs = []
    for i in range(50):
        bulk_logs.append(
            AiEvalLog(
                user_id=test_user.id,
                provider_used="mock_openai",
                model_name="gpt-4o-mini",
                tokens_in=None,
                tokens_out=None,
                latency_ms=None,
                route_chosen=None,
                confidence_score=None,
                pii_fields_masked=None,
                query_summary=f"Null telemetry record {i:03d}",
                created_at=base_time + timedelta(seconds=i),
            )
        )
    db_session.add_all(bulk_logs)
    await db_session.commit()

    # Query page 1 (limit 20)
    p1 = (await async_client.get("/api/v1/ai/eval/history?page=1&limit=20", headers=headers)).json()
    assert p1["total"] == 50
    assert len(p1["items"]) == 20
    assert p1["page"] == 1
    # Check default fallbacks when DB columns are None
    first_item = p1["items"][0]
    assert first_item["tokens_in"] == 0
    assert first_item["tokens_out"] == 0
    assert first_item["latency_ms"] == 0
    assert first_item["route_chosen"] == "coach"
    assert first_item["confidence_score"] == 1.0
    assert first_item["pii_fields_masked"] == 0

    # Query page 2 (limit 20)
    p2 = (await async_client.get("/api/v1/ai/eval/history?page=2&limit=20", headers=headers)).json()
    assert len(p2["items"]) == 20
    assert p2["page"] == 2

    # Query page 3 (limit 20)
    p3 = (await async_client.get("/api/v1/ai/eval/history?page=3&limit=20", headers=headers)).json()
    assert len(p3["items"]) == 10
    assert p3["page"] == 3

