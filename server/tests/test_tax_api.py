"""Integration tests for Tax Management API Router."""
from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Account, Transaction
from app.models.tax import BusinessType, TaxCategory, TaxCategoryType, TaxProfile
from app.models.user import User


@pytest.mark.asyncio
async def test_tax_profile_crud_api(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    # 1. Create Tax Profile
    create_res = await async_client.post(
        "/api/v1/tax/profile",
        json={
            "tax_year": 2026,
            "country": "AU",
            "business_type": "sole_trader",
            "abn": "12 345 678 901",
            "gst_registered": True,
        },
        headers=auth_headers,
    )
    assert create_res.status_code in (200, 201)
    data = create_res.json()
    assert data["abn"] == "12 345 678 901"
    assert data["gst_registered"] is True

    # 2. Get Tax Profile
    get_res = await async_client.get("/api/v1/tax/profile?tax_year=2026", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["business_type"] == "sole_trader"

    # 3. Patch Tax Profile
    patch_res = await async_client.patch(
        "/api/v1/tax/profile?tax_year=2026",
        json={"gst_registered": False},
        headers=auth_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["gst_registered"] is False


@pytest.mark.asyncio
async def test_tax_summary_and_bas_api(
    async_client: AsyncClient,
    test_user: User,
    test_account: Account,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    # Add income transaction
    income_txn = Transaction(
        account_id=test_account.id,
        user_id=test_user.id,
        amount_minor=6500000,
        currency="AUD",
        description="Client Consulting Retainer",
        merchant_raw="Client Retainer",
        merchant_norm="client retainer",
        is_income=True,
        date=date(2026, 2, 15),
    )
    db_session.add(income_txn)
    await db_session.commit()

    # Get tax summary
    sum_res = await async_client.get("/api/v1/tax/summary?tax_year=2026", headers=auth_headers)
    assert sum_res.status_code == 200
    sum_data = sum_res.json()
    assert sum_data["gross_income_minor"] >= 6500000
    assert sum_data["estimated_tax_minor"] > 0

    # Get BAS Q1 report
    bas_res = await async_client.get("/api/v1/tax/bas?tax_year=2026&quarter=1", headers=auth_headers)
    assert bas_res.status_code == 200
    bas_data = bas_res.json()
    assert bas_data["quarter"] == 1
    assert bas_data["g1_total_sales_minor"] >= 6500000


@pytest.mark.asyncio
async def test_tax_deductions_crud_and_suggestions(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    # 1. Post deduction
    post_res = await async_client.post(
        "/api/v1/tax/deductions",
        json={
            "tax_year": 2026,
            "tax_category_code": "D4_TOOLS",
            "amount_minor": 120000,
            "notes": "Monitor for home office",
        },
        headers=auth_headers,
    )
    assert post_res.status_code == 201
    ded_data = post_res.json()
    assert ded_data["amount_minor"] == 120000
    ded_id = ded_data["id"]

    # 2. List deductions
    list_res = await async_client.get("/api/v1/tax/deductions?tax_year=2026", headers=auth_headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 3. Suggestions
    sug_res = await async_client.get("/api/v1/tax/suggestions", headers=auth_headers)
    assert sug_res.status_code == 200

    # 4. Delete deduction
    del_res = await async_client.delete(f"/api/v1/tax/deductions/{ded_id}", headers=auth_headers)
    assert del_res.status_code == 204
