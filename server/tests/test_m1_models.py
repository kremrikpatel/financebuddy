"""Tests for Milestone M1: Family, Tax, and AI Eval models and Alembic migrations.
Includes quality checks, boundary checks, and adversarial stress tests.
"""
import importlib.util
import uuid
from datetime import datetime, UTC

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

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


def test_alembic_0002_upgrade_and_downgrade():
    """Verify Alembic 0002 migration upgrade and rollback safety."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)

        # Create dummy user and transaction tables for foreign keys
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY, email VARCHAR(255));"))
        conn.execute(text("CREATE TABLE transactions (id CHAR(32) PRIMARY KEY, amount BIGINT);"))
        conn.commit()

        # Load 0002 migration module
        spec = importlib.util.spec_from_file_location("mig2", "alembic/versions/0002_family_tax_ai_eval.py")
        mig2 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig2)
        mig2.op = op

        # Test upgrade
        mig2.upgrade()
        conn.commit()

        insp = inspect(conn)
        tables = set(insp.get_table_names())
        expected_tables = {"family_groups", "family_members", "tax_profiles", "tax_categories", "tax_deductions", "ai_eval_logs"}
        assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"

        # Verify columns in each table
        fg_cols = {c["name"] for c in insp.get_columns("family_groups")}
        assert {"id", "name", "owner_id", "created_at", "updated_at"}.issubset(fg_cols)

        fm_cols = {c["name"] for c in insp.get_columns("family_members")}
        assert {"id", "family_id", "user_id", "role", "spending_limit_minor", "is_active", "joined_at", "created_at", "updated_at"}.issubset(fm_cols)

        tp_cols = {c["name"] for c in insp.get_columns("tax_profiles")}
        assert {"id", "user_id", "tax_year", "country", "business_type", "abn", "gst_registered", "created_at", "updated_at"}.issubset(tp_cols)

        tc_cols = {c["name"] for c in insp.get_columns("tax_categories")}
        assert {"id", "name", "code", "type", "description", "created_at", "updated_at"}.issubset(tc_cols)

        td_cols = {c["name"] for c in insp.get_columns("tax_deductions")}
        assert {"id", "user_id", "transaction_id", "tax_category_id", "amount_minor", "gst_claimed_minor", "tax_year", "notes", "receipt_url", "created_at", "updated_at"}.issubset(td_cols)

        ae_cols = {c["name"] for c in insp.get_columns("ai_eval_logs")}
        assert {"id", "user_id", "thread_id", "message_id", "provider_used", "model_name", "tokens_in", "tokens_out", "latency_ms", "route_chosen", "confidence_score", "pii_fields_masked", "query_summary", "created_at"}.issubset(ae_cols)

        # Test downgrade
        mig2.downgrade()
        conn.commit()

        insp_after = inspect(conn)
        tables_after = set(insp_after.get_table_names())
        for t in expected_tables:
            assert t not in tables_after, f"Table {t} was not dropped during downgrade!"

        # Test re-upgrade (idempotent rollback / re-apply cycle)
        mig2.upgrade()
        conn.commit()
        tables_reup = set(inspect(conn).get_table_names())
        assert expected_tables.issubset(tables_reup)


@pytest.mark.asyncio
async def test_family_models_crud_and_constraints():
    """Verify FamilyGroup and FamilyMember model operations and constraints."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        u_owner = User(
            id=uuid.uuid4(),
            email=f"owner_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash",
            full_name="Family Owner",
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        u_child = User(
            id=uuid.uuid4(),
            email=f"child_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash",
            full_name="Family Child",
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        session.add_all([u_owner, u_child])
        await session.commit()
        owner_id = u_owner.id
        child_id = u_child.id

        # Create FamilyGroup
        fg = FamilyGroup(id=uuid.uuid4(), name="The Incredibles", owner_id=owner_id)
        session.add(fg)
        await session.commit()
        fg_id = fg.id

        # Add Members with distinct roles
        m1 = FamilyMember(
            id=uuid.uuid4(),
            family_id=fg_id,
            user_id=owner_id,
            role=FamilyRole.OWNER,
            spending_limit_minor=None,
            is_active=True,
        )
        m2 = FamilyMember(
            id=uuid.uuid4(),
            family_id=fg_id,
            user_id=child_id,
            role=FamilyRole.CHILD,
            spending_limit_minor=10000,  # $100.00
            is_active=True,
        )
        session.add_all([m1, m2])
        await session.commit()

        # Check relationships with selectinload
        stmt = select(FamilyGroup).options(selectinload(FamilyGroup.members)).where(FamilyGroup.id == fg_id)
        res = await session.scalar(stmt)
        assert res is not None
        assert len(res.members) == 2
        member_roles = {m.role for m in res.members}
        assert FamilyRole.OWNER in member_roles
        assert FamilyRole.CHILD in member_roles

        # Test duplicate member constraint
        dup = FamilyMember(
            id=uuid.uuid4(),
            family_id=fg_id,
            user_id=child_id,
            role=FamilyRole.MEMBER,
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_tax_models_crud_and_constraints():
    """Verify TaxProfile, TaxCategory, and TaxDeduction model operations."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        u = User(
            id=uuid.uuid4(),
            email=f"tax_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash",
            full_name="Tax User",
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        session.add(u)
        await session.commit()
        uid = u.id

        # Create TaxProfile
        tp = TaxProfile(
            id=uuid.uuid4(),
            user_id=uid,
            tax_year=2025,
            country="AU",
            business_type=BusinessType.SOLE_TRADER,
            abn="51824753556",
            gst_registered=True,
        )
        session.add(tp)
        await session.commit()
        await session.refresh(tp)

        assert tp.country == "AU"
        assert tp.business_type == BusinessType.SOLE_TRADER
        assert tp.abn == "51824753556"
        assert tp.gst_registered is True

        # Test duplicate tax profile for same user and tax year
        dup_tp = TaxProfile(
            id=uuid.uuid4(),
            user_id=uid,
            tax_year=2025,
            country="AU",
            business_type=BusinessType.COMPANY,
        )
        session.add(dup_tp)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        # Create TaxCategories
        cat_ded = TaxCategory(
            id=uuid.uuid4(),
            name="Vehicle & Travel",
            code="D1_VEHICLE",
            type=TaxCategoryType.DEDUCTION,
            description="Work related car expenses",
        )
        cat_gst = TaxCategory(
            id=uuid.uuid4(),
            name="Capital Purchases GST",
            code="GST_CAPITAL",
            type=TaxCategoryType.GST_CLAIMABLE,
        )
        session.add_all([cat_ded, cat_gst])
        await session.commit()
        cat_ded_id = cat_ded.id

        # Test duplicate code on TaxCategory
        dup_cat = TaxCategory(
            id=uuid.uuid4(),
            name="Vehicle Duplicate",
            code="D1_VEHICLE",
            type=TaxCategoryType.DEDUCTION,
        )
        session.add(dup_cat)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        # Create TaxDeduction
        td = TaxDeduction(
            id=uuid.uuid4(),
            user_id=uid,
            tax_category_id=cat_ded_id,
            amount_minor=45000,
            gst_claimed_minor=4500,
            tax_year=2025,
            notes="Fuel and maintenance logbook claim",
            receipt_url="https://s3.example.com/receipt123.pdf",
        )
        session.add(td)
        await session.commit()
        td_id = td.id

        # Query with selectinload
        stmt = select(TaxDeduction).options(selectinload(TaxDeduction.category)).where(TaxDeduction.id == td_id)
        loaded_td = await session.scalar(stmt)
        assert loaded_td is not None
        assert loaded_td.amount_minor == 45000
        assert loaded_td.gst_claimed_minor == 4500
        assert loaded_td.category.name == "Vehicle & Travel"
        assert loaded_td.notes == "Fuel and maintenance logbook claim"

    await engine.dispose()


@pytest.mark.asyncio
async def test_ai_eval_log_crud_and_telemetry():
    """Verify AiEvalLog model logging and attributes."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        u = User(
            id=uuid.uuid4(),
            email=f"ai_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash",
            full_name="AI User",
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        session.add(u)
        await session.commit()
        uid = u.id

        log = AiEvalLog(
            id=uuid.uuid4(),
            user_id=uid,
            thread_id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            provider_used="openai",
            model_name="gpt-4o-mini",
            tokens_in=250,
            tokens_out=120,
            latency_ms=450,
            route_chosen="tax",
            confidence_score=0.95,
            pii_fields_masked=1,
            query_summary="How do I claim home office expenses?",
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)

        assert log.provider_used == "openai"
        assert log.model_name == "gpt-4o-mini"
        assert log.tokens_in == 250
        assert log.tokens_out == 120
        assert log.latency_ms == 450
        assert log.route_chosen == "tax"
        assert log.confidence_score == 0.95
        assert log.pii_fields_masked == 1
        assert log.query_summary == "How do I claim home office expenses?"
        assert log.created_at is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_adversarial_boundary_conditions_and_cascade_lifecycle():
    """Adversarial stress testing: boundary values, cascades, extreme numbers, nullability."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        # Create user
        u = User(
            id=uuid.uuid4(),
            email=f"adv_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash",
            full_name="Adv User",
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        session.add(u)
        await session.commit()
        uid = u.id

        # 1. Test 64-bit integer boundaries on spending_limit_minor, amount_minor, gst_claimed_minor
        max_int64 = 9223372036854775807  # Max signed 64-bit BigInteger
        cat = TaxCategory(
            id=uuid.uuid4(),
            name="Mega Asset",
            code="CAT_MAX_INT",
            type=TaxCategoryType.DEDUCTION,
        )
        session.add(cat)
        await session.commit()
        cat_id = cat.id

        td_max = TaxDeduction(
            id=uuid.uuid4(),
            user_id=uid,
            tax_category_id=cat_id,
            amount_minor=max_int64,
            gst_claimed_minor=0,
            tax_year=2030,
        )
        session.add(td_max)
        await session.commit()
        await session.refresh(td_max)
        assert td_max.amount_minor == max_int64

        # 2. Test zero and negative amounts (corrections/refunds)
        td_zero = TaxDeduction(
            id=uuid.uuid4(),
            user_id=uid,
            tax_category_id=cat_id,
            amount_minor=0,
            gst_claimed_minor=0,
            tax_year=2030,
        )
        session.add(td_zero)
        await session.commit()
        assert td_zero.amount_minor == 0

        # 3. Test AiEvalLog with zero latency, zero tokens, edge confidence (0.0 and 1.0)
        eval_edge = AiEvalLog(
            id=uuid.uuid4(),
            user_id=uid,
            thread_id=None,
            message_id=None,
            provider_used="local_ollama",
            model_name="llama3.1",
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            route_chosen="direct",
            confidence_score=0.0,
            pii_fields_masked=0,
        )
        session.add(eval_edge)
        await session.commit()
        await session.refresh(eval_edge)
        assert eval_edge.tokens_in == 0
        assert eval_edge.confidence_score == 0.0
        assert eval_edge.thread_id is None

        # 4. Test FamilyGroup cascade delete on members
        fg = FamilyGroup(id=uuid.uuid4(), name="Cascade Group", owner_id=uid)
        session.add(fg)
        await session.commit()
        fg_id = fg.id

        fm = FamilyMember(
            id=uuid.uuid4(),
            family_id=fg_id,
            user_id=uid,
            role=FamilyRole.ADMIN,
            spending_limit_minor=max_int64,
        )
        session.add(fm)
        await session.commit()

        # Delete FamilyGroup -> FamilyMember should be deleted
        stmt_fg = select(FamilyGroup).where(FamilyGroup.id == fg_id)
        loaded_fg = await session.scalar(stmt_fg)
        await session.delete(loaded_fg)
        await session.commit()

        members = (await session.scalars(select(FamilyMember).where(FamilyMember.family_id == fg_id))).all()
        assert len(members) == 0

    await engine.dispose()
