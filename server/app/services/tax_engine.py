"""Australian Tax Calculation Engine and Deduction Recommendation Service.

Implements:
- Australian individual progressive income tax brackets (Stage 3 2024-2026).
- Medicare levy with low-income shade-in phase.
- GST liability & BAS quarter preparation (1A - 1B).
- Deduction summary aggregations by tax category.
- AI & rule-based deductible transaction suggestions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.finance import Transaction
from app.models.tax import TaxCategory, TaxCategoryType, TaxDeduction


# ── AU Tax Brackets (2024-2026 Stage 3) ──────────────────────────────────
# Thresholds in standard AUD dollars
AU_BRACKETS_2024_2026 = [
    (18200, 0.0, 0),             # $0 - $18,200: Nil
    (45000, 0.16, 18200),        # $18,201 - $45,000: 16% on excess over $18,200
    (135000, 0.30, 45000),       # $45,001 - $135,000: $4,288 + 30% on excess over $45,000
    (190000, 0.37, 135000),      # $135,001 - $190,000: $31,288 + 37% on excess over $135,000
    (float("inf"), 0.45, 190000) # $190,001+: $51,638 + 45% on excess over $190,000
]

MEDICARE_LOW_INCOME_THRESHOLD = 26000
MEDICARE_PHASE_IN_UPPER = 32500
MEDICARE_RATE = 0.02
MEDICARE_PHASE_IN_RATE = 0.10


class TaxEstimateResult(BaseModel):
    gross_income_minor: int
    total_deductions_minor: int
    taxable_income_minor: int
    base_tax_minor: int
    medicare_levy_minor: int
    estimated_tax_minor: int
    effective_rate_pct: float
    country: str = "AU"
    currency: str = "AUD"


class GstLiabilityResult(BaseModel):
    quarter: int | None = None
    g1_total_sales_minor: int = 0
    g1a_gst_on_sales_minor: int = 0
    g1b_gst_on_purchases_minor: int = 0
    sales_gst_minor: int = 0
    purchases_gst_minor: int = 0
    net_gst_minor: int = 0
    is_refund: bool = False


class DeductionCategoryBreakdown(BaseModel):
    category_id: str | None = None
    category_name: str
    category_code: str
    total_amount_minor: int
    total_gst_claimed_minor: int
    count: int


class DeductionSummary(BaseModel):
    user_id: str
    tax_year: int
    total_deductions_minor: int
    total_gst_claimed_minor: int
    total_count: int
    categories: list[DeductionCategoryBreakdown]


class DeductionSuggestion(BaseModel):
    transaction_id: str | None = None
    merchant: str
    amount_minor: int
    date: str | None = None
    suggested_category_code: str
    suggested_category_name: str
    reason: str
    confidence: float


def calculate_estimated_tax(
    gross_income_minor: int,
    deductions_minor: int = 0,
    country: str = "AU",
) -> TaxEstimateResult:
    """Calculate Australian estimated income tax and Medicare levy in minor units (cents)."""
    taxable_income_minor = max(0, gross_income_minor - deductions_minor)
    taxable_income = taxable_income_minor / 100.0

    # Calculate progressive income tax
    base_tax = 0.0
    if taxable_income > 190000:
        base_tax = 4288 + 27000 + 20350 + (taxable_income - 190000) * 0.45
    elif taxable_income > 135000:
        base_tax = 4288 + 27000 + (taxable_income - 135000) * 0.37
    elif taxable_income > 45000:
        base_tax = 4288 + (taxable_income - 45000) * 0.30
    elif taxable_income > 18200:
        base_tax = (taxable_income - 18200) * 0.16
    else:
        base_tax = 0.0

    # Calculate Medicare levy with low-income shade-in
    medicare_levy = 0.0
    if taxable_income > MEDICARE_PHASE_IN_UPPER:
        medicare_levy = taxable_income * MEDICARE_RATE
    elif taxable_income > MEDICARE_LOW_INCOME_THRESHOLD:
        medicare_levy = (taxable_income - MEDICARE_LOW_INCOME_THRESHOLD) * MEDICARE_PHASE_IN_RATE
    else:
        medicare_levy = 0.0

    total_tax = base_tax + medicare_levy
    base_tax_minor = round(base_tax * 100)
    medicare_levy_minor = round(medicare_levy * 100)
    estimated_tax_minor = round(total_tax * 100)

    effective_rate_pct = (
        round((estimated_tax_minor / gross_income_minor) * 100.0, 2)
        if gross_income_minor > 0
        else 0.0
    )

    return TaxEstimateResult(
        gross_income_minor=gross_income_minor,
        total_deductions_minor=deductions_minor,
        taxable_income_minor=taxable_income_minor,
        base_tax_minor=base_tax_minor,
        medicare_levy_minor=medicare_levy_minor,
        estimated_tax_minor=estimated_tax_minor,
        effective_rate_pct=effective_rate_pct,
        country=country,
        currency="AUD",
    )


def calculate_gst_liability(
    sales_gst_minor: int = 0,
    purchases_gst_minor: int = 0,
    quarter: int | None = None,
    g1_total_sales_minor: int = 0,
) -> GstLiabilityResult:
    """Calculate Net GST liability or refund from 1A (GST on sales) and 1B (GST on purchases)."""
    net_gst = sales_gst_minor - purchases_gst_minor
    is_refund = net_gst < 0

    return GstLiabilityResult(
        quarter=quarter,
        g1_total_sales_minor=g1_total_sales_minor,
        g1a_gst_on_sales_minor=sales_gst_minor,
        g1b_gst_on_purchases_minor=purchases_gst_minor,
        sales_gst_minor=sales_gst_minor,
        purchases_gst_minor=purchases_gst_minor,
        net_gst_minor=net_gst,
        is_refund=is_refund,
    )


async def get_deduction_summary(
    user_id: uuid.UUID,
    tax_year: int,
    session: AsyncSession,
) -> DeductionSummary:
    """Aggregate claimed tax deductions for a user in a given tax year by category."""
    query = (
        select(TaxDeduction)
        .options(selectinload(TaxDeduction.category))
        .where(
            TaxDeduction.user_id == user_id,
            TaxDeduction.tax_year == tax_year,
        )
    )
    rows = (await session.execute(query)).scalars().all()

    total_amount_minor = 0
    total_gst_claimed_minor = 0
    categories_map: dict[str, dict[str, Any]] = {}

    for d in rows:
        total_amount_minor += d.amount_minor
        total_gst_claimed_minor += d.gst_claimed_minor or 0

        cat_code = d.category.code if d.category else "D5_OTHER"
        cat_name = d.category.name if d.category else "Other Work Deductions"
        cat_id = str(d.category.id) if d.category else None

        if cat_code not in categories_map:
            categories_map[cat_code] = {
                "category_id": cat_id,
                "category_name": cat_name,
                "category_code": cat_code,
                "total_amount_minor": 0,
                "total_gst_claimed_minor": 0,
                "count": 0,
            }

        categories_map[cat_code]["total_amount_minor"] += d.amount_minor
        categories_map[cat_code]["total_gst_claimed_minor"] += d.gst_claimed_minor or 0
        categories_map[cat_code]["count"] += 1

    category_list = [
        DeductionCategoryBreakdown(**cat_data)
        for cat_data in categories_map.values()
    ]

    return DeductionSummary(
        user_id=str(user_id),
        tax_year=tax_year,
        total_deductions_minor=total_amount_minor,
        total_gst_claimed_minor=total_gst_claimed_minor,
        total_count=len(rows),
        categories=category_list,
    )


# Pattern mappings for Australian tax deduction classification
DEDUCTION_RULES = [
    # Tools & Technology (D4_TOOLS)
    (
        r"(?i)(apple|macbook|dell|lenovo|officeworks|jb hi-fi|harvey norman|github|jetbrains|aws|amazon web services|google cloud|azure|digitalocean|adobe|figma|notion|slack|zoom|openai|cursor|sublime|atlassian|docker|datadog|sentry|heroku|vercel|cloudflare|godaddy|namecheap)",
        "D4_TOOLS",
        "Tools and Equipment",
        "Software, cloud infrastructure, developer tools, or computing hardware used for business.",
        0.90,
    ),
    # Home Office Expenses (D2_HOME_OFFICE)
    (
        r"(?i)(telstra|optus|tpg|aussie broadband|vodafone|belong|superloop|ikea|freedom furniture|ergonomic|desk|chair|stationery|monitor arm|origin energy|agl|energyaustralia)",
        "D2_HOME_OFFICE",
        "Home Office Expenses",
        "Home office furniture, utilities, telecommunications, or internet connectivity.",
        0.85,
    ),
    # Car & Business Travel (D1_CAR)
    (
        r"(?i)(qantas|virgin australia|jetstar|uber|didi|13cabs|silver top|caltex|ampol|bp |shell |7-eleven fuel|mobil|toll|linkt|eastlink|citylink|parking|wilson parking|secure parking)",
        "D1_CAR",
        "Work-Related Car Expenses",
        "Work-related travel, transport, parking, tolls, or fuel expenses.",
        0.80,
    ),
    # Self-Education & Professional Development (D3_EDUCATION)
    (
        r"(?i)(udemy|coursera|edx|pluralsight|oreilly|linkedin learning|frontend masters|cloud guru|general assembly|cpa australia|ca anz|law society|acm|ieee|conference|workshop|webinar)",
        "D3_EDUCATION",
        "Self-Education Expenses",
        "Courses, training, books, or conferences directly relevant to current income-earning activities.",
        0.88,
    ),
    # Professional subscriptions and union fees (D5_OTHER)
    (
        r"(?i)(membership|subscription|union|financial review|afr|economist|bloomberg|wall street journal|medium|substack)",
        "D5_OTHER",
        "Other Work Deductions",
        "Professional journals, industry memberships, and work-related subscriptions.",
        0.75,
    ),
]


def suggest_deductions(transactions: list[Transaction | dict[str, Any]]) -> list[DeductionSuggestion]:
    """Scan transactions to detect deductible expenses based on merchant names and descriptions."""
    suggestions: list[DeductionSuggestion] = []

    for item in transactions:
        if isinstance(item, Transaction):
            txn_id = str(item.id)
            merchant = item.merchant_norm or item.merchant_raw or ""
            desc = item.description or ""
            amount_minor = abs(item.amount_minor)
            date_str = item.date.isoformat() if hasattr(item.date, "isoformat") else str(item.date)
            # Only scan expenses (negative amounts or is_income=False)
            if item.amount_minor > 0 and item.is_income:
                continue
        else:
            txn_id = str(item.get("id") or item.get("transaction_id") or "")
            merchant = item.get("merchant") or item.get("merchant_raw") or item.get("merchant_norm") or ""
            desc = item.get("description") or ""
            raw_amt = item.get("amount_minor", 0)
            amount_minor = abs(raw_amt)
            date_str = str(item.get("date") or "")
            if item.get("is_income", False) or raw_amt > 0:
                continue

        text = f"{merchant} {desc}".strip()
        if not text or amount_minor == 0:
            continue

        for pattern, code, name, reason, conf in DEDUCTION_RULES:
            if re.search(pattern, text):
                suggestions.append(
                    DeductionSuggestion(
                        transaction_id=txn_id or None,
                        merchant=merchant or "Expense",
                        amount_minor=amount_minor,
                        date=date_str or None,
                        suggested_category_code=code,
                        suggested_category_name=name,
                        reason=reason,
                        confidence=conf,
                    )
                )
                break

    return suggestions
