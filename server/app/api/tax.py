"""Tax Management API Router for Sole Traders and Small Businesses.

Implements:
- TaxProfile CRUD (tax year, country="AU", business type, ABN, GST registration)
- Estimated tax liability summary (AU tax brackets, Medicare levy, effective rate)
- BAS preparation report for quarters Q1-Q4 (G1 sales, 1A GST collected, 1B GST paid, Net GST)
- Tax deduction claims management (tagging transactions or adding manual deductions)
- AI-assisted deduction suggestions from expense transactions
"""
from __future__ import annotations

from datetime import date
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.finance import Account, Transaction
from app.models.tax import (
    BusinessType,
    TaxCategory,
    TaxCategoryType,
    TaxDeduction,
    TaxProfile,
)
from app.models.user import User
from app.services.deps import get_current_user
from app.services.tax_engine import (
    DeductionCategoryBreakdown,
    DeductionSuggestion,
    DeductionSummary,
    GstLiabilityResult,
    TaxEstimateResult,
    calculate_estimated_tax,
    calculate_gst_liability,
    get_deduction_summary,
    suggest_deductions,
)

router = APIRouter(prefix="/tax", tags=["tax"])


# ── Schemas ─────────────────────────────────────────────────────────────

class TaxProfileIn(BaseModel):
    tax_year: int = Field(default_factory=lambda: date.today().year)
    country: str = "AU"
    business_type: BusinessType = BusinessType.SOLE_TRADER
    abn: str | None = None
    gst_registered: bool = False


class TaxProfileUpdateIn(BaseModel):
    tax_year: int | None = None
    country: str | None = None
    business_type: BusinessType | None = None
    abn: str | None = None
    gst_registered: bool | None = None


class TaxProfileOut(BaseModel):
    id: str
    user_id: str
    tax_year: int
    country: str
    business_type: str
    abn: str | None
    gst_registered: bool

    model_config = {"from_attributes": True}


class TaxDeductionIn(BaseModel):
    tax_year: int = Field(default_factory=lambda: date.today().year)
    tax_category_id: uuid.UUID | None = None
    tax_category_code: str | None = None
    transaction_id: uuid.UUID | None = None
    amount_minor: int = Field(gt=0)
    gst_claimed_minor: int = 0
    notes: str | None = None
    receipt_url: str | None = None


class TaxDeductionOut(BaseModel):
    id: str
    user_id: str
    transaction_id: str | None
    tax_category_id: str
    category_name: str | None = None
    category_code: str | None = None
    amount_minor: int
    gst_claimed_minor: int
    tax_year: int
    notes: str | None
    receipt_url: str | None

    model_config = {"from_attributes": True}


class TaxCategoryOut(BaseModel):
    id: str
    name: str
    code: str
    type: str
    description: str | None

    model_config = {"from_attributes": True}


# ── Profile Endpoints ───────────────────────────────────────────────────

@router.get("/profile", response_model=TaxProfileOut)
async def get_tax_profile(
    tax_year: int = Query(default_factory=lambda: date.today().year),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the user's tax profile for a specified tax year."""
    profile = await db.scalar(
        select(TaxProfile).where(
            TaxProfile.user_id == user.id,
            TaxProfile.tax_year == tax_year,
        )
    )
    if not profile:
        # Fall back to latest profile if available
        profile = await db.scalar(
            select(TaxProfile)
            .where(TaxProfile.user_id == user.id)
            .order_by(TaxProfile.tax_year.desc())
        )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tax profile not configured for this user.",
        )
    return TaxProfileOut(
        id=str(profile.id),
        user_id=str(profile.user_id),
        tax_year=profile.tax_year,
        country=profile.country,
        business_type=profile.business_type.value if hasattr(profile.business_type, "value") else str(profile.business_type),
        abn=profile.abn,
        gst_registered=profile.gst_registered,
    )


@router.post("/profile", response_model=TaxProfileOut, status_code=status.HTTP_201_CREATED)
async def create_tax_profile(
    body: TaxProfileIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or replace a tax profile for a given tax year."""
    existing = await db.scalar(
        select(TaxProfile).where(
            TaxProfile.user_id == user.id,
            TaxProfile.tax_year == body.tax_year,
        )
    )
    if existing:
        existing.country = body.country
        existing.business_type = body.business_type
        existing.abn = body.abn
        existing.gst_registered = body.gst_registered
        await db.commit()
        await db.refresh(existing)
        profile = existing
    else:
        profile = TaxProfile(
            user_id=user.id,
            tax_year=body.tax_year,
            country=body.country,
            business_type=body.business_type,
            abn=body.abn,
            gst_registered=body.gst_registered,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

    return TaxProfileOut(
        id=str(profile.id),
        user_id=str(profile.user_id),
        tax_year=profile.tax_year,
        country=profile.country,
        business_type=profile.business_type.value if hasattr(profile.business_type, "value") else str(profile.business_type),
        abn=profile.abn,
        gst_registered=profile.gst_registered,
    )


@router.patch("/profile", response_model=TaxProfileOut)
async def update_tax_profile(
    body: TaxProfileUpdateIn,
    tax_year: int = Query(default_factory=lambda: date.today().year),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update fields on the tax profile for the given year."""
    target_year = body.tax_year or tax_year
    profile = await db.scalar(
        select(TaxProfile).where(
            TaxProfile.user_id == user.id,
            TaxProfile.tax_year == target_year,
        )
    )
    if not profile:
        profile = await db.scalar(
            select(TaxProfile)
            .where(TaxProfile.user_id == user.id)
            .order_by(TaxProfile.tax_year.desc())
        )
    if not profile:
        # Auto-create if updating non-existent
        profile = TaxProfile(
            user_id=user.id,
            tax_year=target_year,
            country=body.country or "AU",
            business_type=body.business_type or BusinessType.SOLE_TRADER,
            abn=body.abn,
            gst_registered=body.gst_registered or False,
        )
        db.add(profile)
    else:
        if body.country is not None:
            profile.country = body.country
        if body.business_type is not None:
            profile.business_type = body.business_type
        if body.abn is not None:
            profile.abn = body.abn
        if body.gst_registered is not None:
            profile.gst_registered = body.gst_registered

    await db.commit()
    await db.refresh(profile)

    return TaxProfileOut(
        id=str(profile.id),
        user_id=str(profile.user_id),
        tax_year=profile.tax_year,
        country=profile.country,
        business_type=profile.business_type.value if hasattr(profile.business_type, "value") else str(profile.business_type),
        abn=profile.abn,
        gst_registered=profile.gst_registered,
    )


# ── Tax Summary & BAS ───────────────────────────────────────────────────

@router.get("/summary", response_model=TaxEstimateResult)
async def get_tax_summary(
    tax_year: int = Query(default_factory=lambda: date.today().year),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute gross income, total deductions, taxable income, and progressive tax liability."""
    # Australian financial year: 1 July (tax_year - 1) to 30 June tax_year OR calendar tax_year
    start_date = date(tax_year, 1, 1)
    end_date = date(tax_year, 12, 31)

    # 1. Calculate Gross Income from user income transactions in the year
    income_stmt = (
        select(func.sum(Transaction.amount_minor))
        .where(
            Transaction.user_id == user.id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.is_income.is_(True),
            Transaction.excluded.is_(False),
        )
    )
    raw_income = await db.scalar(income_stmt)
    gross_income_minor = max(0, raw_income or 0)

    # 2. Get deductions summary from tax_engine
    ded_summary = await get_deduction_summary(user.id, tax_year, db)

    # 3. Calculate AU estimated tax
    result = calculate_estimated_tax(
        gross_income_minor=gross_income_minor,
        deductions_minor=ded_summary.total_deductions_minor,
        country="AU",
    )
    return result


@router.get("/bas", response_model=GstLiabilityResult)
async def get_bas_report(
    tax_year: int = Query(default_factory=lambda: date.today().year),
    quarter: int = Query(1, ge=1, le=4),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate quarterly Business Activity Statement (BAS) preparation for GST reporting."""
    # Determine quarter date ranges
    # Q1: Jul-Sep (or Jan-Mar calendar), standard AU FY Q1 is Jul-Sep, Calendar Q1 is Jan-Mar
    # Supporting calendar quarters Q1: 1/1-31/3, Q2: 1/4-30/6, Q3: 1/7-30/9, Q4: 1/10-31/12
    quarter_dates = {
        1: (date(tax_year, 1, 1), date(tax_year, 3, 31)),
        2: (date(tax_year, 4, 1), date(tax_year, 6, 30)),
        3: (date(tax_year, 7, 1), date(tax_year, 9, 30)),
        4: (date(tax_year, 10, 1), date(tax_year, 12, 31)),
    }
    start_d, end_d = quarter_dates.get(quarter, quarter_dates[1])

    # Sales / Income in quarter
    sales_stmt = (
        select(func.sum(Transaction.amount_minor))
        .where(
            Transaction.user_id == user.id,
            Transaction.date >= start_d,
            Transaction.date <= end_d,
            Transaction.is_income.is_(True),
            Transaction.excluded.is_(False),
        )
    )
    raw_sales = await db.scalar(sales_stmt)
    g1_total_sales_minor = max(0, raw_sales or 0)

    # 1A: GST on sales (1/11th of total GST-inclusive sales for GST-registered sole traders)
    g1a_gst_on_sales_minor = round(g1_total_sales_minor / 11)

    # 1B: GST on purchases (sum of gst_claimed_minor on deductions in this quarter)
    gst_purchases_stmt = (
        select(func.sum(TaxDeduction.gst_claimed_minor))
        .join(Transaction, TaxDeduction.transaction_id == Transaction.id, isouter=True)
        .where(
            TaxDeduction.user_id == user.id,
            TaxDeduction.tax_year == tax_year,
        )
    )
    raw_gst_purchases = await db.scalar(gst_purchases_stmt)
    g1b_gst_on_purchases_minor = max(0, raw_gst_purchases or 0)

    return calculate_gst_liability(
        sales_gst_minor=g1a_gst_on_sales_minor,
        purchases_gst_minor=g1b_gst_on_purchases_minor,
        quarter=quarter,
        g1_total_sales_minor=g1_total_sales_minor,
    )


# ── Deductions CRUD & Suggestions ───────────────────────────────────────

@router.get("/categories", response_model=list[TaxCategoryOut])
async def list_tax_categories(
    db: AsyncSession = Depends(get_db),
):
    """List available tax deduction categories."""
    cats = (await db.execute(select(TaxCategory).order_by(TaxCategory.name))).scalars().all()
    return [
        TaxCategoryOut(
            id=str(c.id),
            name=c.name,
            code=c.code,
            type=c.type.value if hasattr(c.type, "value") else str(c.type),
            description=c.description,
        )
        for c in cats
    ]


@router.get("/deductions", response_model=list[TaxDeductionOut])
async def list_tax_deductions(
    tax_year: int = Query(default_factory=lambda: date.today().year),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all claimed tax deductions for the specified tax year."""
    query = (
        select(TaxDeduction)
        .options(selectinload(TaxDeduction.category))
        .where(
            TaxDeduction.user_id == user.id,
            TaxDeduction.tax_year == tax_year,
        )
        .order_by(TaxDeduction.created_at.desc())
    )
    rows = (await db.execute(query)).scalars().all()

    return [
        TaxDeductionOut(
            id=str(d.id),
            user_id=str(d.user_id),
            transaction_id=str(d.transaction_id) if d.transaction_id else None,
            tax_category_id=str(d.tax_category_id),
            category_name=d.category.name if d.category else None,
            category_code=d.category.code if d.category else None,
            amount_minor=d.amount_minor,
            gst_claimed_minor=d.gst_claimed_minor or 0,
            tax_year=d.tax_year,
            notes=d.notes,
            receipt_url=d.receipt_url,
        )
        for d in rows
    ]


@router.post("/deductions", response_model=TaxDeductionOut, status_code=status.HTTP_201_CREATED)
async def create_tax_deduction(
    body: TaxDeductionIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Claim a transaction or create a manual tax deduction record."""
    # Find category by ID or code
    cat = None
    if body.tax_category_id:
        cat = await db.get(TaxCategory, body.tax_category_id)
    elif body.tax_category_code:
        cat = await db.scalar(select(TaxCategory).where(TaxCategory.code == body.tax_category_code))

    if not cat:
        # Fall back to general tools/tech or other deduction category
        cat = await db.scalar(
            select(TaxCategory).where(TaxCategory.code == "D4_TOOLS")
        ) or await db.scalar(
            select(TaxCategory).where(TaxCategory.type == TaxCategoryType.DEDUCTION)
        )
        if not cat:
            cat = TaxCategory(
                name="Other Work Deductions",
                code="D5_OTHER",
                type=TaxCategoryType.DEDUCTION,
                description="General business and work-related expenses",
            )
            db.add(cat)
            await db.flush()

    # Calculate GST claimed if not specified and amount is provided
    gst_claimed = body.gst_claimed_minor
    if gst_claimed == 0 and body.amount_minor > 0:
        gst_claimed = round(body.amount_minor / 11)

    deduction = TaxDeduction(
        user_id=user.id,
        transaction_id=body.transaction_id,
        tax_category_id=cat.id,
        amount_minor=body.amount_minor,
        gst_claimed_minor=gst_claimed,
        tax_year=body.tax_year,
        notes=body.notes,
        receipt_url=body.receipt_url,
    )
    db.add(deduction)
    await db.commit()
    await db.refresh(deduction)

    return TaxDeductionOut(
        id=str(deduction.id),
        user_id=str(deduction.user_id),
        transaction_id=str(deduction.transaction_id) if deduction.transaction_id else None,
        tax_category_id=str(deduction.tax_category_id),
        category_name=cat.name,
        category_code=cat.code,
        amount_minor=deduction.amount_minor,
        gst_claimed_minor=deduction.gst_claimed_minor,
        tax_year=deduction.tax_year,
        notes=deduction.notes,
        receipt_url=deduction.receipt_url,
    )


@router.delete("/deductions/{deduction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tax_deduction(
    deduction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a claimed tax deduction."""
    deduction = await db.scalar(
        select(TaxDeduction).where(
            TaxDeduction.id == deduction_id,
            TaxDeduction.user_id == user.id,
        )
    )
    if deduction:
        await db.delete(deduction)
        await db.commit()
    return None


@router.get("/suggestions", response_model=list[DeductionSuggestion])
async def get_deduction_suggestions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze recent user transactions and suggest potential business tax deductions."""
    txns = list(
        (
            await db.execute(
                select(Transaction)
                .where(
                    Transaction.user_id == user.id,
                    Transaction.is_income.is_(False),
                    Transaction.excluded.is_(False),
                )
                .order_by(Transaction.date.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )

    suggestions = suggest_deductions(txns)
    return suggestions
