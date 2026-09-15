"""Unit and integration tests for Australian Tax Engine Service."""
from __future__ import annotations

from datetime import date
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Account, Transaction
from app.models.tax import TaxCategory, TaxCategoryType, TaxDeduction, TaxProfile
from app.models.user import User
from app.services.tax_engine import (
    calculate_estimated_tax,
    calculate_gst_liability,
    get_deduction_summary,
    suggest_deductions,
)


def test_calculate_estimated_tax_zero_and_low_income():
    # Under tax-free threshold ($18,200)
    res = calculate_estimated_tax(gross_income_minor=1500000, deductions_minor=0)
    assert res.taxable_income_minor == 1500000
    assert res.base_tax_minor == 0
    assert res.medicare_levy_minor == 0
    assert res.estimated_tax_minor == 0
    assert res.effective_rate_pct == 0.0


def test_calculate_estimated_tax_brackets_stage3():
    # $30,000 income -> 16% on ($30,000 - $18,200) = 16% of $11,800 = $1,888 base tax
    # $30,000 taxable -> shade-in Medicare: ($30,000 - $26,000) * 10% = $400
    res = calculate_estimated_tax(gross_income_minor=3000000, deductions_minor=0)
    assert res.taxable_income_minor == 3000000
    assert res.base_tax_minor == 188800
    assert res.medicare_levy_minor == 40000
    assert res.estimated_tax_minor == 228800
    assert res.effective_rate_pct == 7.63

    # $80,000 income -> $4,288 + 30% of ($80,000 - $45,000) = $4,288 + $10,500 = $14,788
    # Medicare levy = 2% of $80,000 = $1,600
    res2 = calculate_estimated_tax(gross_income_minor=8000000, deductions_minor=0)
    assert res2.base_tax_minor == 1478800
    assert res2.medicare_levy_minor == 160000
    assert res2.estimated_tax_minor == 1638800

    # $150,000 income with $10,000 deductions -> taxable $140,000
    # $140,000 income -> $31,288 + 37% of ($140,000 - $135,000) = $31,288 + $1,850 = $33,138
    # Medicare = 2% of $140,000 = $2,800
    res3 = calculate_estimated_tax(gross_income_minor=15000000, deductions_minor=1000000)
    assert res3.taxable_income_minor == 14000000
    assert res3.base_tax_minor == 3313800
    assert res3.medicare_levy_minor == 280000
    assert res3.estimated_tax_minor == 3593800


def test_calculate_gst_liability():
    # Sales GST = $5,000, Purchases GST = $1,200 -> Net GST = $3,800 payable
    gst_res = calculate_gst_liability(sales_gst_minor=500000, purchases_gst_minor=120000, quarter=1)
    assert gst_res.sales_gst_minor == 500000
    assert gst_res.purchases_gst_minor == 120000
    assert gst_res.net_gst_minor == 380000
    assert gst_res.is_refund is False
    assert gst_res.quarter == 1

    # Refund case: Purchases GST > Sales GST
    refund_res = calculate_gst_liability(sales_gst_minor=200000, purchases_gst_minor=350000)
    assert refund_res.net_gst_minor == -150000
    assert refund_res.is_refund is True


@pytest.mark.asyncio
async def test_get_deduction_summary(db_session: AsyncSession, test_user: User):
    cat_tools = TaxCategory(name="Tools & Equipment", code="D4_TOOLS", type=TaxCategoryType.DEDUCTION)
    cat_car = TaxCategory(name="Work Car", code="D1_CAR", type=TaxCategoryType.DEDUCTION)
    db_session.add_all([cat_tools, cat_car])
    await db_session.flush()

    d1 = TaxDeduction(
        user_id=test_user.id,
        tax_category_id=cat_tools.id,
        amount_minor=150000,
        gst_claimed_minor=13636,
        tax_year=2026,
    )
    d2 = TaxDeduction(
        user_id=test_user.id,
        tax_category_id=cat_tools.id,
        amount_minor=50000,
        gst_claimed_minor=4545,
        tax_year=2026,
    )
    d3 = TaxDeduction(
        user_id=test_user.id,
        tax_category_id=cat_car.id,
        amount_minor=80000,
        gst_claimed_minor=7272,
        tax_year=2026,
    )
    db_session.add_all([d1, d2, d3])
    await db_session.commit()

    summary = await get_deduction_summary(test_user.id, 2026, db_session)
    assert summary.total_deductions_minor == 280000
    assert summary.total_gst_claimed_minor == 25453
    assert summary.total_count == 3
    assert len(summary.categories) == 2


def test_suggest_deductions_patterns():
    txns = [
        {
            "id": "1",
            "merchant": "Apple Store Sydney",
            "description": "MacBook Pro laptop",
            "amount_minor": -349900,
            "is_income": False,
            "date": "2026-04-10",
        },
        {
            "id": "2",
            "merchant": "Telstra",
            "description": "NBN High Speed Internet",
            "amount_minor": -11000,
            "is_income": False,
            "date": "2026-04-12",
        },
        {
            "id": "3",
            "merchant": "Uber",
            "description": "Trip to client office",
            "amount_minor": -4500,
            "is_income": False,
            "date": "2026-04-15",
        },
        {
            "id": "4",
            "merchant": "Salary Payment",
            "description": "Monthly pay",
            "amount_minor": 850000,
            "is_income": True,
            "date": "2026-04-01",
        },
    ]

    suggestions = suggest_deductions(txns)
    assert len(suggestions) == 3
    codes = {s.suggested_category_code for s in suggestions}
    assert "D4_TOOLS" in codes
    assert "D2_HOME_OFFICE" in codes
    assert "D1_CAR" in codes
