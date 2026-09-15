"""Integration tests for Banking Providers and Stripe Integration."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.providers import StripeProvider, available_providers, get_providers


def test_australian_banks_registered_in_provider_registry():
    providers = get_providers()
    assert "basiq" in providers
    assert "stripe" in providers

    expected_au_banks = [
        "cba",
        "westpac",
        "anz",
        "nab",
        "macquarie",
        "suncorp",
        "bendigo",
        "boq",
        "ing_au",
        "up",
    ]
    for bank in expected_au_banks:
        assert bank in providers
        p = providers[bank]
        assert p.region == "AU"


def test_available_providers_regional_groupings():
    provs = available_providers()
    regions = {p["region"] for p in provs}
    assert "AU" in regions
    assert "Business" in regions
    assert "US" in regions
    assert "EU" in regions


@pytest.mark.asyncio
async def test_stripe_connect_and_webhook_api(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    # Connect Stripe
    res = await async_client.post(
        "/api/v1/connections/stripe/connect",
        json={"api_key": "sk_test_mock_secret_key_12345"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "connected"
    assert data["provider"] == "stripe"

    # Webhook charge.succeeded event
    webhook_payload = {
        "id": "evt_test_charge_999",
        "type": "charge.succeeded",
        "data": {
            "object": {
                "id": "ch_test_999",
                "amount": 75000,
                "currency": "aud",
                "description": "Invoice #552 Payment",
                "customer": "Customer Pty Ltd",
            }
        },
    }
    wh_res = await async_client.post(
        "/api/v1/connections/stripe/webhook",
        json=webhook_payload,
        headers={"Stripe-Signature": "t=123,v1=sig"},
    )
    assert wh_res.status_code == 200
    assert wh_res.json()["status"] == "processed"
