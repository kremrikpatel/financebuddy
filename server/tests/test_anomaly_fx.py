"""Unit tests for Anomaly detection, FX service, and Mock Bank Provider."""
import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction
from app.services import anomaly, fx
from app.services.providers import MockBankProvider, get_providers


def test_ewma_spike_detection():
    # Normal spending around $50
    history = [5000.0] * 10
    # $50 candidate is normal
    assert anomaly.ewma_spike(history, 5000.0) == 0.0
    # $500 candidate is massive outlier
    spike_score = anomaly.ewma_spike(history, 50000.0)
    assert spike_score is not None and spike_score >= 3.0


def test_velocity_burst():
    user_id = uuid.uuid4()
    acct_id = uuid.uuid4()
    today = date.today()
    txns = [
        Transaction(
            account_id=acct_id,
            user_id=user_id,
            date=today,
            amount_minor=-1000 * i,
            merchant_raw=f"Shop {i}",
        )
        for i in range(1, 8)
    ]
    assert anomaly.velocity_burst(txns) is True
    # 4 txns is below threshold
    assert anomaly.velocity_burst(txns[:4]) is False


@pytest.mark.asyncio
async def test_fx_rate_and_conversion(db_session: AsyncSession):
    # Same currency
    assert await fx.get_rate(db_session, "EUR", "EUR") == 1.0

    # Fallback rate conversion USD -> GBP
    converted = await fx.convert_minor(db_session, 10000, "USD", "GBP")
    assert converted == 7900  # 100 * 0.79 = 79.00 -> 7900 minor

    # Fallback rate conversion USD -> JPY
    converted_jpy = await fx.convert_minor(db_session, 10000, "USD", "JPY")
    assert converted_jpy == 1505000

    # Unknown currency pair raises ValueError
    with pytest.raises(ValueError):
        await fx.get_rate(db_session, "FAKE1", "FAKE2")


@pytest.mark.asyncio
async def test_mock_bank_provider():
    provider = MockBankProvider("mock")
    assert provider.is_configured() is True
    link = await provider.create_link("user-123", None)
    assert "link_token" in link

    ext_id = await provider.exchange("public-token-abc")
    assert ext_id.startswith("mock_item_")

    class DummyConn:
        external_id = "mock-123"

    accounts = await provider.fetch_accounts(DummyConn())
    assert len(accounts) == 3
    txns = await provider.fetch_transactions(DummyConn())
    assert len(txns) >= 2


def test_registry_includes_mock_provider():
    providers = get_providers()
    assert "mock" in providers
    assert "sandbox" in providers
