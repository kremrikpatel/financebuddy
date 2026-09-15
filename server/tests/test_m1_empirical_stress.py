"""Empirical stress test suite for Milestone M1 (Family, Tax, AI Eval models & Alembic migration)."""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from datetime import UTC, datetime

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from pgvector.sqlalchemy import Vector
from sqlalchemy import StaticPool, create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

# Add server directory to sys.path if not present
server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from app.db.base import Base
from app.models import (
    Account,
    AiEvalLog,
    BusinessType,
    FamilyGroup,
    FamilyMember,
    FamilyRole,
    TaxCategory,
    TaxCategoryType,
    TaxDeduction,
    TaxProfile,
    Transaction,
    User,
)


@compiles(Vector, "sqlite")
def compile_vector_sqlite(type_, compiler, **kw):
    return "TEXT"


def _enable_sqlite_fk(dbapi_con, con_record):
    cursor = dbapi_con.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
async def stress_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    event.listen(engine.sync_engine, "connect", _enable_sqlite_fk)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_metadata_tables_and_columns():
    """Verify all M1 tables, columns, types, nullability, and primary keys exist in metadata."""
    tables = Base.metadata.tables

    # Check table existence
    assert "family_groups" in tables
    assert "family_members" in tables
    assert "tax_profiles" in tables
    assert "tax_categories" in tables
    assert "tax_deductions" in tables
    assert "ai_eval_logs" in tables

    # Check FamilyGroup columns
    fg_cols = tables["family_groups"].columns
    assert "id" in fg_cols and fg_cols["id"].primary_key
    assert "name" in fg_cols and not fg_cols["name"].nullable
    assert "owner_id" in fg_cols and not fg_cols["owner_id"].nullable
    assert "created_at" in fg_cols
    assert "updated_at" in fg_cols

    # Check FamilyMember columns
    fm_cols = tables["family_members"].columns
    assert "id" in fm_cols and fm_cols["id"].primary_key
    assert "family_id" in fm_cols and not fm_cols["family_id"].nullable
    assert "user_id" in fm_cols and not fm_cols["user_id"].nullable
    assert "role" in fm_cols
    assert "spending_limit_minor" in fm_cols and fm_cols["spending_limit_minor"].nullable
    assert "is_active" in fm_cols
    assert "joined_at" in fm_cols

    # Check TaxProfile columns
    tp_cols = tables["tax_profiles"].columns
    assert "id" in tp_cols and tp_cols["id"].primary_key
    assert "user_id" in tp_cols and not tp_cols["user_id"].nullable
    assert "tax_year" in tp_cols and not tp_cols["tax_year"].nullable
    assert "country" in tp_cols
    assert "business_type" in tp_cols
    assert "abn" in tp_cols and tp_cols["abn"].nullable
    assert "gst_registered" in tp_cols

    # Check TaxCategory columns
    tc_cols = tables["tax_categories"].columns
    assert "id" in tc_cols and tc_cols["id"].primary_key
    assert "name" in tc_cols and not tc_cols["name"].nullable
    assert "code" in tc_cols and not tc_cols["code"].nullable
    assert "type" in tc_cols
    assert "description" in tc_cols and tc_cols["description"].nullable

    # Check TaxDeduction columns
    td_cols = tables["tax_deductions"].columns
    assert "id" in td_cols and td_cols["id"].primary_key
    assert "user_id" in td_cols and not td_cols["user_id"].nullable
    assert "transaction_id" in td_cols and td_cols["transaction_id"].nullable
    assert "tax_category_id" in td_cols and not td_cols["tax_category_id"].nullable
    assert "amount_minor" in td_cols and not td_cols["amount_minor"].nullable
    assert "gst_claimed_minor" in td_cols
    assert "tax_year" in td_cols and not td_cols["tax_year"].nullable
    assert "notes" in td_cols and td_cols["notes"].nullable
    assert "receipt_url" in td_cols and td_cols["receipt_url"].nullable

    # Check AiEvalLog columns
    ae_cols = tables["ai_eval_logs"].columns
    assert "id" in ae_cols and ae_cols["id"].primary_key
    assert "user_id" in ae_cols and not ae_cols["user_id"].nullable
    assert "thread_id" in ae_cols and ae_cols["thread_id"].nullable
    assert "message_id" in ae_cols and ae_cols["message_id"].nullable
    assert "provider_used" in ae_cols and not ae_cols["provider_used"].nullable
    assert "model_name" in ae_cols and not ae_cols["model_name"].nullable
    assert "tokens_in" in ae_cols
    assert "tokens_out" in ae_cols
    assert "latency_ms" in ae_cols
    assert "route_chosen" in ae_cols
    assert "confidence_score" in ae_cols
    assert "pii_fields_masked" in ae_cols
    assert "query_summary" in ae_cols and ae_cols["query_summary"].nullable
    assert "created_at" in ae_cols


@pytest.mark.asyncio
async def test_crud_model_instantiation_and_relationships(stress_db):
    """Test full instantiation, saving, queries, and ORM relationship navigation."""
    session, _engine = stress_db

    # Create users
    owner = User(id=uuid.uuid4(), email="owner@test.com", password_hash="hash")
    member_user = User(id=uuid.uuid4(), email="member@test.com", password_hash="hash")
    session.add_all([owner, member_user])
    await session.commit()

    # Create FamilyGroup
    family = FamilyGroup(name="The Smiths", owner_id=owner.id)
    session.add(family)
    await session.commit()

    # Create FamilyMembers
    fm_owner = FamilyMember(family_id=family.id, user_id=owner.id, role=FamilyRole.OWNER)
    fm_member = FamilyMember(
        family_id=family.id,
        user_id=member_user.id,
        role=FamilyRole.MEMBER,
        spending_limit_minor=50000,
    )
    session.add_all([fm_owner, fm_member])
    await session.commit()

    # Create TaxProfile
    tax_profile = TaxProfile(
        user_id=owner.id,
        tax_year=2025,
        country="AU",
        business_type=BusinessType.SOLE_TRADER,
        abn="12345678901",
        gst_registered=True,
    )
    session.add(tax_profile)

    # Create TaxCategory
    tax_cat = TaxCategory(
        name="Office Supplies",
        code="OFFICE_SUPPLIES",
        type=TaxCategoryType.DEDUCTION,
        description="Expenses on stationery and desk items",
    )
    session.add(tax_cat)
    await session.commit()

    # Create Account & Transaction
    acct = Account(id=uuid.uuid4(), user_id=owner.id, name="Checking", balance_minor=100000)
    session.add(acct)
    await session.commit()

    txn = Transaction(
        id=uuid.uuid4(),
        account_id=acct.id,
        user_id=owner.id,
        date=datetime.now(UTC).date(),
        amount_minor=-15000,
        merchant_raw="Officeworks",
        merchant_norm="officeworks",
    )
    session.add(txn)
    await session.commit()

    # Create TaxDeduction
    deduction = TaxDeduction(
        user_id=owner.id,
        transaction_id=txn.id,
        tax_category_id=tax_cat.id,
        amount_minor=15000,
        gst_claimed_minor=1364,
        tax_year=2025,
        notes="New monitor stand",
        receipt_url="https://s3.example.com/receipts/1.pdf",
    )
    session.add(deduction)

    # Create AiEvalLog
    eval_log = AiEvalLog(
        user_id=owner.id,
        thread_id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        provider_used="anthropic",
        model_name="claude-3-5-sonnet-20241022",
        tokens_in=250,
        tokens_out=480,
        latency_ms=1200,
        route_chosen="tax",
        confidence_score=0.98,
        pii_fields_masked=2,
        query_summary="Can I claim my monitor stand as an instant asset write-off?",
    )
    session.add(eval_log)
    await session.commit()

    # Query and assert ORM relationships
    res_family = await session.scalar(select(FamilyGroup).where(FamilyGroup.id == family.id))
    assert res_family is not None
    assert res_family.name == "The Smiths"
    assert res_family.owner.email == "owner@test.com"

    res_members = (await session.scalars(select(FamilyMember).where(FamilyMember.family_id == family.id))).all()
    assert len(res_members) == 2
    assert {m.role for m in res_members} == {FamilyRole.OWNER, FamilyRole.MEMBER}

    res_deduction = await session.scalar(select(TaxDeduction).where(TaxDeduction.id == deduction.id))
    assert res_deduction is not None
    assert res_deduction.user.email == "owner@test.com"
    assert res_deduction.transaction.merchant_raw == "Officeworks"
    assert res_deduction.category.code == "OFFICE_SUPPLIES"
    assert res_deduction.gst_claimed_minor == 1364

    res_eval = await session.scalar(select(AiEvalLog).where(AiEvalLog.id == eval_log.id))
    assert res_eval is not None
    assert res_eval.route_chosen == "tax"
    assert res_eval.confidence_score == 0.98
    assert res_eval.user.email == "owner@test.com"


@pytest.mark.asyncio
async def test_foreign_key_cascades_and_set_null(stress_db):
    """Test foreign key constraint cascades and set null behaviors."""
    session, _engine = stress_db

    # Setup User, FamilyGroup, Member, TaxProfile, TaxCategory, Account, Transaction, TaxDeduction, AiEvalLog
    user = User(id=uuid.uuid4(), email="cascade_user@test.com", password_hash="hash")
    session.add(user)
    await session.commit()

    fg = FamilyGroup(name="Cascade Family", owner_id=user.id)
    session.add(fg)
    await session.commit()

    fm = FamilyMember(family_id=fg.id, user_id=user.id, role=FamilyRole.OWNER)
    tp = TaxProfile(user_id=user.id, tax_year=2025, business_type=BusinessType.COMPANY)
    tc = TaxCategory(name="Travel", code="TRAVEL", type=TaxCategoryType.DEDUCTION)
    acct = Account(id=uuid.uuid4(), user_id=user.id, name="Checking", balance_minor=50000)
    session.add_all([fm, tp, tc, acct])
    await session.commit()

    txn = Transaction(
        id=uuid.uuid4(),
        account_id=acct.id,
        user_id=user.id,
        date=datetime.now(UTC).date(),
        amount_minor=-2000,
        merchant_raw="Train Ticket",
    )
    session.add(txn)
    await session.commit()

    td = TaxDeduction(
        user_id=user.id,
        transaction_id=txn.id,
        tax_category_id=tc.id,
        amount_minor=2000,
        tax_year=2025,
    )
    ae = AiEvalLog(
        user_id=user.id,
        provider_used="openai",
        model_name="gpt-4o",
    )
    session.add_all([td, ae])
    await session.commit()

    td_id = td.id
    fg_id = fg.id
    fm_id = fm.id
    tp_id = tp.id
    ae_id = ae.id
    user_id = user.id

    # 1. Deleting Transaction must set TaxDeduction.transaction_id to NULL (SET NULL)
    await session.delete(txn)
    await session.commit()

    session.expire_all()
    td_check = await session.scalar(select(TaxDeduction).where(TaxDeduction.id == td_id))
    assert td_check is not None
    assert td_check.transaction_id is None, "TaxDeduction.transaction_id was not set to NULL upon Transaction deletion"

    # 2. Deleting TaxCategory while referenced by TaxDeduction must raise IntegrityError (RESTRICT)
    await session.delete(tc)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # 3. Deleting User must cascade delete FamilyGroup, FamilyMember, TaxProfile, TaxDeduction, AiEvalLog
    user_to_delete = await session.scalar(select(User).where(User.id == user_id))
    await session.delete(user_to_delete)
    await session.commit()

    session.expire_all()
    assert await session.scalar(select(FamilyGroup).where(FamilyGroup.id == fg_id)) is None
    assert await session.scalar(select(FamilyMember).where(FamilyMember.id == fm_id)) is None
    assert await session.scalar(select(TaxProfile).where(TaxProfile.id == tp_id)) is None
    assert await session.scalar(select(TaxDeduction).where(TaxDeduction.id == td_id)) is None
    assert await session.scalar(select(AiEvalLog).where(AiEvalLog.id == ae_id)) is None


@pytest.mark.asyncio
async def test_unique_constraints(stress_db):
    """Test unique constraints across all M1 models."""
    session, _engine = stress_db

    u1 = User(id=uuid.uuid4(), email="u1@test.com", password_hash="h")
    u2 = User(id=uuid.uuid4(), email="u2@test.com", password_hash="h")
    session.add_all([u1, u2])
    await session.commit()

    u1_id = u1.id

    fg = FamilyGroup(name="Unique Family", owner_id=u1_id)
    session.add(fg)
    await session.commit()
    fg_id = fg.id

    # 1. Test uq_family_member (family_id, user_id)
    fm1 = FamilyMember(family_id=fg_id, user_id=u1_id, role=FamilyRole.OWNER)
    session.add(fm1)
    await session.commit()

    fm_dup = FamilyMember(family_id=fg_id, user_id=u1_id, role=FamilyRole.MEMBER)
    session.add(fm_dup)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # 2. Test uq_tax_profile_user_year (user_id, tax_year)
    tp1 = TaxProfile(user_id=u1_id, tax_year=2025, business_type=BusinessType.SOLE_TRADER)
    session.add(tp1)
    await session.commit()

    tp_dup = TaxProfile(user_id=u1_id, tax_year=2025, business_type=BusinessType.COMPANY)
    session.add(tp_dup)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # Verify same user can have multiple DIFFERENT tax years
    tp_2024 = TaxProfile(user_id=u1_id, tax_year=2024, business_type=BusinessType.SOLE_TRADER)
    tp_2026 = TaxProfile(user_id=u1_id, tax_year=2026, business_type=BusinessType.SOLE_TRADER)
    session.add_all([tp_2024, tp_2026])
    await session.commit()
    profiles = (await session.scalars(select(TaxProfile).where(TaxProfile.user_id == u1_id))).all()
    assert len(profiles) == 3

    # 3. Test TaxCategory code uniqueness
    tc1 = TaxCategory(name="Advertising", code="ADV", type=TaxCategoryType.DEDUCTION)
    session.add(tc1)
    await session.commit()

    tc_dup = TaxCategory(name="Adv Duplicate", code="ADV", type=TaxCategoryType.DEDUCTION)
    session.add(tc_dup)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_boundary_and_edge_cases(stress_db):
    """Stress-test BigInteger bounds, None spending limits, negative/zero deductions, extreme texts."""
    session, _engine = stress_db

    u = User(id=uuid.uuid4(), email="edge_user@test.com", password_hash="h")
    session.add(u)
    await session.commit()
    u_id = u.id

    fg = FamilyGroup(name="Edge Family", owner_id=u_id)
    tc = TaxCategory(name="Edge Category", code="EDGE_CAT", type=TaxCategoryType.DEDUCTION)
    session.add_all([fg, tc])
    await session.commit()
    fg_id = fg.id
    tc_id = tc.id

    # 1. FamilyMember spending limit edge cases
    # Case A: None (unlimited)
    fm_none = FamilyMember(family_id=fg_id, user_id=u_id, spending_limit_minor=None)
    session.add(fm_none)
    await session.commit()
    assert fm_none.spending_limit_minor is None
    await session.delete(fm_none)
    await session.commit()

    # Case B: Max 64-bit BigInteger value (9223372036854775807)
    max_bigint = 9223372036854775807
    fm_max = FamilyMember(family_id=fg_id, user_id=u_id, spending_limit_minor=max_bigint)
    session.add(fm_max)
    await session.commit()
    fm_max_id = fm_max.id
    session.expire_all()
    loaded_fm = await session.scalar(select(FamilyMember).where(FamilyMember.id == fm_max_id))
    assert loaded_fm.spending_limit_minor == max_bigint
    await session.delete(loaded_fm)
    await session.commit()

    # Case C: Zero spending limit
    fm_zero = FamilyMember(family_id=fg_id, user_id=u_id, spending_limit_minor=0)
    session.add(fm_zero)
    await session.commit()
    fm_zero_id = fm_zero.id
    session.expire_all()
    loaded_fm_zero = await session.scalar(select(FamilyMember).where(FamilyMember.id == fm_zero_id))
    assert loaded_fm_zero.spending_limit_minor == 0

    # 2. TaxDeduction amount edge cases
    # Case A: Zero amount
    td_zero = TaxDeduction(user_id=u_id, tax_category_id=tc_id, amount_minor=0, gst_claimed_minor=0, tax_year=2025)
    # Case B: Negative amount (e.g. refund/reversal)
    td_neg = TaxDeduction(user_id=u_id, tax_category_id=tc_id, amount_minor=-50000, gst_claimed_minor=-4545, tax_year=2025)
    # Case C: Maximum BigInteger amount
    td_max = TaxDeduction(user_id=u_id, tax_category_id=tc_id, amount_minor=max_bigint, gst_claimed_minor=1000000000, tax_year=2025)
    # Case D: Large note / receipt URL
    long_notes = "Tax Note: " + ("ABCDE12345 " * 2000)  # 22,000 chars
    long_url = "https://example.com/receipts/" + ("x" * 2000) + ".pdf"
    td_notes = TaxDeduction(
        user_id=u_id,
        tax_category_id=tc_id,
        amount_minor=1000,
        tax_year=2025,
        notes=long_notes,
        receipt_url=long_url,
    )
    session.add_all([td_zero, td_neg, td_max, td_notes])
    await session.commit()

    td_max_id = td_max.id
    td_notes_id = td_notes.id
    session.expire_all()

    loaded_td_max = await session.scalar(select(TaxDeduction).where(TaxDeduction.id == td_max_id))
    assert loaded_td_max.amount_minor == max_bigint

    loaded_td_notes = await session.scalar(select(TaxDeduction).where(TaxDeduction.id == td_notes_id))
    assert loaded_td_notes.notes == long_notes
    assert loaded_td_notes.receipt_url == long_url

    # 3. AiEvalLog extreme query_summary (100,000 characters with unicode & emojis)
    extreme_summary = "📈 Financial Query 🇦🇺: " + ("Australian Tax Assessment BAS FY2025-2026 §12-B \u2602 " * 2000)
    ae_extreme = AiEvalLog(
        user_id=u_id,
        thread_id=None,
        message_id=None,
        provider_used="google",
        model_name="gemini-1.5-pro",
        tokens_in=150000,
        tokens_out=8000,
        latency_ms=95000,
        route_chosen="tax",
        confidence_score=0.00001,
        pii_fields_masked=99,
        query_summary=extreme_summary,
    )
    session.add(ae_extreme)
    await session.commit()
    ae_extreme_id = ae_extreme.id
    session.expire_all()

    loaded_ae = await session.scalar(select(AiEvalLog).where(AiEvalLog.id == ae_extreme_id))
    assert loaded_ae.query_summary == extreme_summary
    assert loaded_ae.thread_id is None
    assert loaded_ae.message_id is None
    assert loaded_ae.tokens_in == 150000
    assert loaded_ae.latency_ms == 95000


@pytest.mark.asyncio
async def test_enum_types_and_defaults(stress_db):
    """Verify enum serialization, string equality, and model column default values."""
    session, _engine = stress_db

    # 1. Verify Enum string inheritance and values
    assert FamilyRole.OWNER == "owner"
    assert FamilyRole.ADMIN == "admin"
    assert FamilyRole.MEMBER == "member"
    assert FamilyRole.CHILD == "child"
    assert set(FamilyRole) == {FamilyRole.OWNER, FamilyRole.ADMIN, FamilyRole.MEMBER, FamilyRole.CHILD}

    assert BusinessType.SOLE_TRADER == "sole_trader"
    assert BusinessType.COMPANY == "company"
    assert BusinessType.PARTNERSHIP == "partnership"
    assert set(BusinessType) == {BusinessType.SOLE_TRADER, BusinessType.COMPANY, BusinessType.PARTNERSHIP}

    assert TaxCategoryType.DEDUCTION == "deduction"
    assert TaxCategoryType.INCOME == "income"
    assert TaxCategoryType.GST_CLAIMABLE == "gst_claimable"
    assert set(TaxCategoryType) == {TaxCategoryType.DEDUCTION, TaxCategoryType.INCOME, TaxCategoryType.GST_CLAIMABLE}

    # 2. Verify model defaults when instantiated without optional params
    u = User(id=uuid.uuid4(), email="defaults_user@test.com", password_hash="h")
    session.add(u)
    await session.commit()
    u_id = u.id

    fg = FamilyGroup(name="Default Test Family", owner_id=u_id)
    session.add(fg)
    await session.commit()
    fg_id = fg.id

    fm = FamilyMember(family_id=fg_id, user_id=u_id)
    tp = TaxProfile(user_id=u_id, tax_year=2025)
    tc = TaxCategory(name="Generic Category", code="GEN_CAT")
    session.add_all([fm, tp, tc])
    await session.commit()

    fm_id = fm.id
    tp_id = tp.id
    tc_id = tc.id

    td = TaxDeduction(user_id=u_id, tax_category_id=tc_id, amount_minor=5000, tax_year=2025)
    ae = AiEvalLog(user_id=u_id, provider_used="openai", model_name="gpt-4o")
    session.add_all([td, ae])
    await session.commit()

    td_id = td.id
    ae_id = ae.id
    session.expire_all()

    # Assert defaults persisted correctly
    loaded_fm = await session.scalar(select(FamilyMember).where(FamilyMember.id == fm_id))
    assert loaded_fm.role == FamilyRole.MEMBER
    assert loaded_fm.is_active is True
    assert loaded_fm.spending_limit_minor is None
    assert isinstance(loaded_fm.joined_at, datetime)

    loaded_tp = await session.scalar(select(TaxProfile).where(TaxProfile.id == tp_id))
    assert loaded_tp.country == "AU"
    assert loaded_tp.business_type == BusinessType.SOLE_TRADER
    assert loaded_tp.gst_registered is False
    assert loaded_tp.abn is None

    loaded_tc = await session.scalar(select(TaxCategory).where(TaxCategory.id == tc_id))
    assert loaded_tc.type == TaxCategoryType.DEDUCTION
    assert loaded_tc.description is None

    loaded_td = await session.scalar(select(TaxDeduction).where(TaxDeduction.id == td_id))
    assert loaded_td.gst_claimed_minor == 0
    assert loaded_td.notes is None
    assert loaded_td.receipt_url is None

    loaded_ae = await session.scalar(select(AiEvalLog).where(AiEvalLog.id == ae_id))
    assert loaded_ae.tokens_in == 0
    assert loaded_ae.tokens_out == 0
    assert loaded_ae.latency_ms == 0
    assert loaded_ae.route_chosen == "coach"
    assert loaded_ae.confidence_score == 1.0
    assert loaded_ae.pii_fields_masked == 0
    assert loaded_ae.query_summary is None


@pytest.mark.asyncio
async def test_foreign_key_violations(stress_db):
    """Verify that inserting records referencing non-existent foreign keys fails."""
    session, _engine = stress_db
    non_existent_id = uuid.uuid4()

    # 1. FamilyGroup with invalid owner_id
    fg_invalid = FamilyGroup(name="Invalid Owner", owner_id=non_existent_id)
    session.add(fg_invalid)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # 2. FamilyMember with invalid family_id or user_id
    u = User(id=uuid.uuid4(), email="fk_user@test.com", password_hash="h")
    session.add(u)
    await session.commit()
    u_id = u.id

    fm_invalid = FamilyMember(family_id=non_existent_id, user_id=u_id)
    session.add(fm_invalid)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # 3. TaxProfile with invalid user_id
    tp_invalid = TaxProfile(user_id=non_existent_id, tax_year=2025)
    session.add(tp_invalid)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # 4. TaxDeduction with invalid tax_category_id
    td_invalid = TaxDeduction(user_id=u_id, tax_category_id=non_existent_id, amount_minor=100, tax_year=2025)
    session.add(td_invalid)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # 5. AiEvalLog with invalid user_id
    ae_invalid = AiEvalLog(user_id=non_existent_id, provider_used="openai", model_name="gpt-4o")
    session.add(ae_invalid)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


def test_alembic_upgrade_and_downgrade_lifecycle():
    """Test Alembic migrations 0001 -> 0002 upgrade and 0002 -> 0001 downgrade lifecycle."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_db_path = tmp.name

    try:
        sqlite_url = f"sqlite:///{tmp_db_path.replace(os.sep, '/')}"
        sync_engine = create_engine(sqlite_url)

        import importlib.util
        path_v1 = os.path.join(server_dir, "alembic", "versions", "0001_initial_schema.py")
        spec1 = importlib.util.spec_from_file_location("migration_0001", path_v1)
        v1 = importlib.util.module_from_spec(spec1)
        spec1.loader.exec_module(v1)

        path_v2 = os.path.join(server_dir, "alembic", "versions", "0002_family_tax_ai_eval.py")
        spec2 = importlib.util.spec_from_file_location("migration_0002", path_v2)
        v2 = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(v2)

        # 1. Execute 0001_initial_schema upgrade
        with sync_engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                v1.upgrade()
            conn.commit()

        from sqlalchemy import inspect
        inspector = inspect(sync_engine)
        t_0001 = set(inspector.get_table_names())
        assert "users" in t_0001
        assert "transactions" in t_0001
        assert "family_groups" not in t_0001
        assert "tax_profiles" not in t_0001
        assert "ai_eval_logs" not in t_0001

        # 2. Execute 0002_family_tax_ai_eval upgrade
        with sync_engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                v2.upgrade()
            conn.commit()

        inspector = inspect(sync_engine)
        t_0002 = set(inspector.get_table_names())
        new_tables = {"family_groups", "family_members", "tax_profiles", "tax_categories", "tax_deductions", "ai_eval_logs"}
        assert new_tables.issubset(t_0002), f"Missing tables after upgrade: {new_tables - t_0002}"

        # Check indexes created on new tables
        fg_indexes = {idx["name"] for idx in inspector.get_indexes("family_groups")}
        assert "ix_family_groups_owner_id" in fg_indexes

        fm_indexes = {idx["name"] for idx in inspector.get_indexes("family_members")}
        assert "ix_family_members_family_id" in fm_indexes
        assert "ix_family_members_user_id" in fm_indexes

        tp_indexes = {idx["name"] for idx in inspector.get_indexes("tax_profiles")}
        assert "ix_tax_profiles_tax_year" in tp_indexes
        assert "ix_tax_profiles_user_id" in tp_indexes
        assert "ix_tax_profile_user_year" in tp_indexes

        tc_indexes = {idx["name"] for idx in inspector.get_indexes("tax_categories")}
        assert "ix_tax_categories_code" in tc_indexes

        td_indexes = {idx["name"] for idx in inspector.get_indexes("tax_deductions")}
        assert "ix_tax_deductions_tax_category_id" in td_indexes
        assert "ix_tax_deductions_tax_year" in td_indexes
        assert "ix_tax_deductions_transaction_id" in td_indexes
        assert "ix_tax_deductions_user_id" in td_indexes
        assert "ix_tax_deductions_user_year" in td_indexes

        ae_indexes = {idx["name"] for idx in inspector.get_indexes("ai_eval_logs")}
        assert "ix_ai_eval_logs_created_at" in ae_indexes
        assert "ix_ai_eval_logs_message_id" in ae_indexes
        assert "ix_ai_eval_logs_thread_id" in ae_indexes
        assert "ix_ai_eval_logs_user_id" in ae_indexes

        # Insert dummy data into each table before downgrade
        u_id = uuid.uuid4().hex
        fg_id = uuid.uuid4().hex
        tc_id = uuid.uuid4().hex
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        with sync_engine.connect() as conn:
            conn.execute(text(f"INSERT INTO users (id, email, locale, base_currency, is_active, is_superuser, mfa_enabled, created_at, updated_at) VALUES ('{u_id}', 'mig_user@test.com', 'en', 'AUD', 1, 0, 0, '{now_str}', '{now_str}')"))
            conn.execute(text(f"INSERT INTO family_groups (id, name, owner_id, created_at, updated_at) VALUES ('{fg_id}', 'Mig Family', '{u_id}', '{now_str}', '{now_str}')"))
            conn.execute(text(f"INSERT INTO family_members (id, family_id, user_id, role, is_active, joined_at, created_at, updated_at) VALUES ('{uuid.uuid4().hex}', '{fg_id}', '{u_id}', 'owner', 1, '{now_str}', '{now_str}', '{now_str}')"))
            conn.execute(text(f"INSERT INTO tax_profiles (id, user_id, tax_year, country, business_type, gst_registered, created_at, updated_at) VALUES ('{uuid.uuid4().hex}', '{u_id}', 2025, 'AU', 'sole_trader', 0, '{now_str}', '{now_str}')"))
            conn.execute(text(f"INSERT INTO tax_categories (id, name, code, type, created_at, updated_at) VALUES ('{tc_id}', 'Supplies', 'SUP', 'deduction', '{now_str}', '{now_str}')"))
            conn.execute(text(f"INSERT INTO tax_deductions (id, user_id, tax_category_id, amount_minor, gst_claimed_minor, tax_year, created_at, updated_at) VALUES ('{uuid.uuid4().hex}', '{u_id}', '{tc_id}', 5000, 0, 2025, '{now_str}', '{now_str}')"))
            conn.execute(text(f"INSERT INTO ai_eval_logs (id, user_id, provider_used, model_name, tokens_in, tokens_out, latency_ms, route_chosen, confidence_score, pii_fields_masked, created_at) VALUES ('{uuid.uuid4().hex}', '{u_id}', 'openai', 'gpt-4o', 10, 20, 100, 'coach', 1.0, 0, '{now_str}')"))
            conn.commit()

        # 3. Execute 0002_family_tax_ai_eval downgrade (even with active rows)
        with sync_engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                v2.downgrade()
            conn.commit()

        inspector = inspect(sync_engine)
        t_downgraded = set(inspector.get_table_names())
        for tbl in new_tables:
            assert tbl not in t_downgraded, f"Table {tbl} was not dropped on downgrade"
        assert "users" in t_downgraded
        assert "transactions" in t_downgraded

        # 4. Re-execute 0002_family_tax_ai_eval upgrade
        with sync_engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                v2.upgrade()
            conn.commit()

        inspector = inspect(sync_engine)
        t_reupgraded = set(inspector.get_table_names())
        assert new_tables.issubset(t_reupgraded)

        sync_engine.dispose()
    finally:
        import contextlib
        with contextlib.suppress(OSError):
            if os.path.exists(tmp_db_path):
                os.remove(tmp_db_path)
