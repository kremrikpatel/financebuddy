"""Tier 2 E2E Boundary and Corner Case Tests.

Comprehensive testing of edge conditions, extreme inputs, and failure modes:
1. Empty payloads & whitespace strings
2. Zero, negative, and extreme numeric boundaries
3. Max-length strings & payload size limits
4. Expired, malformed, and forged tokens
5. Leap years, date boundaries, and month transitions
6. Non-ASCII, Unicode, emoji, and RTL strings
7. Extreme z-scores and zero-variance baselines
8. Unsupported/exotic currencies & minor unit conversions
9. Luhn card checksum & complex PII masking edge cases
"""
from __future__ import annotations

import datetime as dt
import uuid
from datetime import date, timedelta

import httpx
import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pii import mask_pii
from app.core.config import settings
from app.core.security import create_access_token, decode_token
from app.models import Account, Category, User
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


# ============================================================================
# 1. Empty payloads & whitespace strings (≥5 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_auth_login_empty_and_whitespace_fields(async_client: httpx.AsyncClient):
    # Empty email
    resp1 = await async_client.post("/api/v1/auth/login", json={"email": "", "password": "123"})
    assert resp1.status_code == 422

    # Whitespace-only email
    resp2 = await async_client.post("/api/v1/auth/login", json={"email": "   ", "password": "123"})
    assert resp2.status_code in (401, 422)


def test_csv_parse_empty_payload():
    assert importers.parse_csv(b"") == []
    assert importers.parse_csv(b"\n\n\n") == []
    assert importers.parse_csv(b"Date,Amount,Merchant\n") == []


@pytest.mark.asyncio
async def test_chat_send_empty_and_whitespace_message(
    async_client: httpx.AsyncClient, auth_headers: dict[str, str]
):
    # Empty message violates min_length=1
    resp = await async_client.post(
        "/api/v1/chat/send", headers=auth_headers, json={"message": ""}
    )
    assert resp.status_code == 422


def test_merchant_normalizer_empty_and_whitespace():
    assert categorizer.normalize_merchant("") == ""
    assert categorizer.normalize_merchant("   \t\n  ") == ""
    assert categorizer.normalize_merchant("### *** ---") == ""


def test_zero_based_check_empty_envelopes():
    res = budget_engine.zero_based_check([], 0)
    assert res["balanced"] is True
    assert res["unassigned_minor"] == 0


# ============================================================================
# 2. Zero, negative, and extreme numeric boundaries (≥5 tests)
# ============================================================================

def test_zero_based_budget_zero_income_with_allocation():
    res = budget_engine.zero_based_check([{"allocated_minor": 1000}], 0)
    assert res["balanced"] is False
    assert res["unassigned_minor"] == -1000


def test_debt_zero_apr_and_zero_extra_payment():
    debts = [
        {"name": "0% Loan", "principal_minor": 100_000, "apr_bps": 0, "min_payment_minor": 10_000}
    ]
    sim = goals_debt.simulate_payoff(debts, extra_payment_minor=0, strategy="snowball")
    assert sim["total_interest_minor"] == 0
    assert len(sim["schedule"]) == 10  # 100k / 10k = 10 months


@pytest.mark.asyncio
async def test_extreme_numeric_values_in_transactions(
    db_session: AsyncSession, test_account: Account
):
    # Extremely large amount: 90 billion dollars in minor units (fits in 64-bit int)
    large_amount = 9_000_000_000_000_00
    txn, created = await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=date(2026, 1, 1),
        amount_minor=large_amount,
        merchant_raw="Sovereign Fund Deposit",
    )
    assert created is True
    assert txn.amount_minor == large_amount


@pytest.mark.asyncio
async def test_smallest_currency_minor_unit_transaction(
    db_session: AsyncSession, test_account: Account
):
    # 1 minor unit = 1 cent ($0.01)
    txn, created = await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=date(2026, 1, 1),
        amount_minor=-1,
        merchant_raw="Penny Test Charge",
    )
    assert created is True
    assert txn.amount_minor == -1


def test_forecast_all_zero_historical_net_flow():
    nets = [0] * 12
    fc = forecaster.forecast_net_flow(nets, horizon=6)
    assert all(val == 0 for val in fc["forecast"])


# ============================================================================
# 3. Max-length strings & payload size limits (≥5 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_chat_message_8000_char_boundary(
    async_client: httpx.AsyncClient, auth_headers: dict[str, str]
):
    # Exactly 8000 chars should pass validation
    msg_8000 = "A" * 8000
    resp1 = await async_client.post(
        "/api/v1/chat/send", headers=auth_headers, json={"message": msg_8000}
    )
    assert resp1.status_code == 200

    # 8001 chars violates max_length=8000
    msg_8001 = "A" * 8001
    resp2 = await async_client.post(
        "/api/v1/chat/send", headers=auth_headers, json={"message": msg_8001}
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_receipt_ocr_8mb_boundary(
    async_client: httpx.AsyncClient, auth_headers: dict[str, str]
):
    # 8MB + 1 byte rejected
    over_limit = b"x" * (8 * 1024 * 1024 + 1)
    resp = await async_client.post(
        "/api/v1/receipts/scan",
        headers=auth_headers,
        files={"file": ("receipt.jpg", over_limit, "image/jpeg")},
    )
    assert resp.status_code == 413


def test_merchant_normalizer_handles_long_string():
    long_raw = "SUPERMARKET " + ("CHAIN STORE " * 100) + "PTY LTD REF#12345"
    norm = categorizer.normalize_merchant(long_raw)
    assert "supermarket" in norm
    assert "pty ltd" not in norm
    assert "ref" not in norm


def test_rag_chunk_text_very_long_document():
    long_doc = "\n\n".join([f"Section {i} with detailed financial policy content." for i in range(100)])
    chunks = _chunk_text(long_doc, size=500)
    assert len(chunks) > 10
    assert all(len(c["text"]) <= 800 for c in chunks)


def _chunk_text(text: str, size: int) -> list[dict]:
    from app.ai.rag import _chunk_text as ct
    return ct(text, size)


# ============================================================================
# 4. Expired, malformed, and forged tokens (≥5 tests)
# ============================================================================

def test_jwt_expired_token_rejection():
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
    expired_payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": past - dt.timedelta(minutes=15),
        "exp": past,
    }
    expired_token = jwt.encode(expired_payload, settings.secret_key, algorithm="HS256")
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(expired_token)


def test_jwt_forged_secret_rejection():
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": dt.datetime.now(dt.UTC),
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    }
    forged_token = jwt.encode(payload, "wrong-secret-key-1234567890123456", algorithm="HS256")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(forged_token)


@pytest.mark.asyncio
async def test_api_rejects_refresh_token_as_bearer_token(
    async_client: httpx.AsyncClient, auth_tokens: dict[str, str]
):
    # Using refresh token on protected route expecting access token
    headers = {"Authorization": f"Bearer {auth_tokens['refresh_token']}"}
    resp = await async_client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_refresh_with_malformed_token_string(async_client: httpx.AsyncClient):
    resp = await async_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_passkey_finish_with_invalid_challenge_token(async_client: httpx.AsyncClient):
    resp = await async_client.post(
        "/api/v1/auth/passkeys/auth/finish",
        json={"challenge_token": "invalid.jwt.token", "credential": {}},
    )
    assert resp.status_code == 400


# ============================================================================
# 5. Leap years, date boundaries, and month transitions (≥5 tests)
# ============================================================================

def test_csv_date_parser_leap_year_dates():
    # Feb 29 on leap year 2024 is valid
    assert importers._parse_date("2024-02-29") == date(2024, 2, 29)
    assert importers._parse_date("29/02/2028") == date(2028, 2, 29)

    # Feb 29 on non-leap year 2026 must fail
    with pytest.raises(ValueError):
        importers._parse_date("2026-02-29")


def test_budget_month_bounds_calculation_across_months():
    # February 2026 (non-leap) -> 28 days
    start_feb, end_feb = budget_engine.month_bounds(2026, 2)
    assert start_feb == date(2026, 2, 1)
    assert end_feb == date(2026, 2, 28)

    # February 2024 (leap year) -> 29 days
    start_leap, end_leap = budget_engine.month_bounds(2024, 2)
    assert end_leap == date(2024, 2, 29)

    # December 2026 -> 31 days
    start_dec, end_dec = budget_engine.month_bounds(2026, 12)
    assert end_dec == date(2026, 12, 31)

    # April 2026 -> 30 days
    start_apr, end_apr = budget_engine.month_bounds(2026, 4)
    assert end_apr == date(2026, 4, 30)


@pytest.mark.asyncio
async def test_transactions_across_year_boundary(
    db_session: AsyncSession, test_account: Account
):
    await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=date(2025, 12, 31),
        amount_minor=-5000,
        merchant_raw="New Year Eve Dinner",
    )
    await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=date(2026, 1, 1),
        amount_minor=-2000,
        merchant_raw="New Year Day Brunch",
    )
    flows = await txn_service.monthly_flows(db_session, test_account.user_id, months=6)
    months = {f["month"] for f in flows}
    assert "2025-12" in months
    assert "2026-01" in months


def test_csv_parser_with_historical_and_future_dates():
    csv_content = (
        b"Date,Amount,Merchant\n"
        b"1980-05-12,-10.00,Retro Store\n"
        b"2099-12-31,-100.00,Future Store\n"
    )
    txns = importers.parse_csv(csv_content)
    assert len(txns) == 2
    assert txns[0].date == date(1980, 5, 12)
    assert txns[1].date == date(2099, 12, 31)


# ============================================================================
# 6. Non-ASCII, Unicode, emoji, and RTL strings (≥5 tests)
# ============================================================================

def test_merchant_normalizer_arabic_and_rtl():
    arabic_raw = "سوبرماركت كارفور دبي"
    norm = categorizer.normalize_merchant(arabic_raw)
    assert len(norm) > 0
    assert "كارفور" in norm


def test_merchant_normalizer_cjk_characters():
    cjk_raw = "セブン-イレブン 渋谷店"
    norm = categorizer.normalize_merchant(cjk_raw)
    assert len(norm) > 0
    assert "イレブン" in norm


@pytest.mark.asyncio
async def test_transaction_with_emojis_in_description_and_tags(
    db_session: AsyncSession, test_account: Account
):
    txn, created = await txn_service.create_transaction(
        db_session,
        account=test_account,
        date=date(2026, 3, 10),
        amount_minor=-4500,
        merchant_raw="Sushi Train 🍣🍱",
        description="Dinner with friends 🎉🥂",
        tags=["food-lover-🍜", "weekend-🌟"],
    )
    assert created is True
    assert "🍣" in txn.merchant_raw
    assert "🎉" in txn.description
    assert "food-lover-🍜" in txn.tags


def test_merchant_normalizer_european_accents_and_legal_suffixes():
    accented = "Café François & Crêperie S.A.S."
    norm = categorizer.normalize_merchant(accented)
    assert "caf" in norm
    assert "cr" in norm
    assert "sas" not in norm


def test_csv_parser_utf8_bom_and_special_characters():
    # UTF-8 with BOM (\xef\xbb\xbf)
    csv_bytes = (
        b"\xef\xbb\xbfDate,Amount,Merchant,Description\n"
        b'2026-03-01,-25.00,"Boutique & Cadeaux \"L\'etoile\"","Cadeau d\'anniversaire \xc2\xa350"\n'
    )
    txns = importers.parse_csv(csv_bytes)
    assert len(txns) == 1
    assert "Boutique" in txns[0].merchant_raw


# ============================================================================
# 7. Extreme z-scores and zero-variance baselines (≥5 tests)
# ============================================================================

def test_zscore_zero_variance_identical_baseline():
    history = [5000.0] * 15
    # Equal to mean -> 0 sigma
    assert anomaly.zscore_spike(history, 5000.0) == 0.0
    # Greater than mean with 0 std -> returns bounded 5.0 sigma
    assert anomaly.zscore_spike(history, 5001.0) == 5.0
    # Less than mean with 0 std -> returns None
    assert anomaly.zscore_spike(history, 4999.0) is None


def test_zscore_extreme_outlier_scale():
    history = [100.0, 105.0, 95.0, 102.0, 98.0, 101.0, 99.0, 100.0]
    z = anomaly.zscore_spike(history, 1_000_000.0)
    assert z is not None
    assert z > 1000.0


def test_zscore_below_minimum_history():
    assert anomaly.zscore_spike([10.0, 20.0, 30.0], 100.0, min_history=8) is None


def test_forecaster_spikes_handles_flat_series():
    daily_flat = [(f"2026-01-{(d % 28) + 1:02d}", 1000) for d in range(30)]
    assert forecaster.spending_spikes(daily_flat) == []


# ============================================================================
# 8. Unsupported/exotic currencies & minor unit conversions (≥5 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_fx_rate_same_unsupported_currency(db_session: AsyncSession):
    # Same currency always returns 1.0 even if exotic
    assert await fx.get_rate(db_session, "XYZ", "XYZ") == 1.0


@pytest.mark.asyncio
async def test_fx_rate_unsupported_pair_raises_value_error(db_session: AsyncSession):
    with pytest.raises(ValueError) as exc:
        await fx.get_rate(db_session, "FOO", "BAR")
    assert "No FX rate available" in str(exc.value)


@pytest.mark.asyncio
async def test_fx_convert_zero_minor_amount(db_session: AsyncSession):
    converted = await fx.convert_minor(db_session, 0, "USD", "EUR")
    assert converted == 0


@pytest.mark.asyncio
async def test_fx_convert_high_rate_currency_jpy(db_session: AsyncSession):
    # Fallback USD->JPY is 150.5
    # $100.00 (10000 minor) -> 1505000 minor units
    converted = await fx.convert_minor(db_session, 10000, "USD", "JPY")
    assert converted == 1505000


@pytest.mark.asyncio
async def test_fx_rate_inverse_conversion(db_session: AsyncSession):
    rate_usd_aud = await fx.get_rate(db_session, "USD", "AUD")
    rate_aud_usd = await fx.get_rate(db_session, "AUD", "USD")
    assert abs((rate_usd_aud * rate_aud_usd) - 1.0) < 0.01


# ============================================================================
# 9. Luhn card checksum & complex PII masking edge cases (≥5 tests)
# ============================================================================

def test_pii_masking_amex_15_digit_card():
    # Valid 15-digit Amex starting with 37
    amex_valid = "378282246310005"
    masked = mask_pii(f"Amex card {amex_valid} for payment")
    assert "[CARD]" in masked
    assert amex_valid not in masked


def test_pii_masking_invalid_luhn_number_preserved():
    # 16 digits failing Luhn
    invalid_card = "4532015112830367"
    masked = mask_pii(f"Transaction ID {invalid_card}")
    assert invalid_card in masked
    assert "[CARD]" not in masked


def test_pii_masking_multiple_entities_in_single_prompt():
    prompt = (
        "User Alice (alice@corp.internal, phone +1 (555) 234-5678) requested a refund "
        "of $500 for card 4532015112830366 transferred to IBAN DE89370400440532013000."
    )
    masked = mask_pii(prompt)
    assert "[EMAIL]" in masked
    assert "[PHONE]" in masked
    assert "[CARD]" in masked
    assert "[IBAN]" in masked
    assert "alice@corp.internal" not in masked
    assert "4532015112830366" not in masked
    assert "DE89370400440532013000" not in masked


def test_pii_masking_adjacent_punctuation_and_delimiters():
    text = '("test.user+tag@domain.co.uk", card:4532015112830366;)'
    masked = mask_pii(text)
    assert "[EMAIL]" in masked
    assert "[CARD]" in masked


def test_pii_masking_clean_text_unchanged():
    plain = "Monthly grocery budget allocation of $500 across 3 categories."
    assert mask_pii(plain) == plain
