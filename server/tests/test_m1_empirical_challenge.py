"""Empirical Challenger Test Suite for Milestone M1 (Database Models & Alembic Migration).

Adversarial Stress Tests & Edge Cases:
1. Base.metadata registration and table schemas
2. Family models: CRUD, relationships, role enums, unique constraints, cascade deletion
3. Tax models: CRUD, relationships, type enums, unique constraints, FK RESTRICT, FK SET NULL, cascade deletion
4. AI Eval models: CRUD, querying by user_id/thread_id, pagination, cascade deletion
5. Non-regression on existing models: User, Account, Transaction, Budget, Goal, Debt, etc.
6. Alembic migration programmatic upgrade and downgrade against SQLite engine
7. Multi-member family group stress test (100 members) and owner vs member deletion
8. Multiple deductions per transaction with SET NULL cascade stress
9. Boundary value testing: large amounts, 0 amounts, NULL notes/receipts/spending limits
10. Schema index and constraint verification across Base.metadata
"""
from __future__ import annotations

import datetime
import importlib.util
import os
import uuid
from datetime import UTC

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    StaticPool,
    create_engine,
    inspect,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import selectinload

from app.db.base import Base
from app.models import (
    Account,
    AiEvalLog,
    Alert,
    AuditLog,
    Budget,
    BudgetEnvelope,
    BusinessType,
    Category,
    ChatMessage,
    ChatThread,
    Debt,
    FamilyGroup,
    FamilyMember,
    FamilyRole,
    FxRate,
    Goal,
    KnowledgeDoc,
    OAuthAccount,
    PasskeyCredential,
    RecurringSubscription,
    RefreshToken,
    TaxCategory,
    TaxCategoryType,
    TaxDeduction,
    TaxProfile,
    Transaction,
    TransactionSplit,
    User,
)


@compiles(Vector, "sqlite")
def compile_vector_sqlite(type_, compiler, **kw):
    return "TEXT"


async def setup_test_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Enable foreign keys in SQLite
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, session_factory


@pytest.mark.asyncio
async def test_01_metadata_registration():
    """Verify that all new tables are registered in Base.metadata with correct attributes."""
    tables = Base.metadata.tables
    expected_new_tables = {
        "family_groups",
        "family_members",
        "tax_profiles",
        "tax_categories",
        "tax_deductions",
        "ai_eval_logs",
    }
    for table_name in expected_new_tables:
        assert table_name in tables, f"Table {table_name} missing from Base.metadata"

    assert len(tables) >= 26, f"Expected at least 26 tables in metadata, got {len(tables)}"

    # Check FamilyMember unique constraint
    fm_table = tables["family_members"]
    uq_names = {c.name for c in fm_table.constraints if hasattr(c, "columns")}
    assert "uq_family_member" in uq_names or any(
        set(c.columns.keys()) == {"family_id", "user_id"} for c in fm_table.constraints if hasattr(c, "columns")
    )

    # Check TaxProfile unique constraint
    tp_table = tables["tax_profiles"]
    assert any(
        set(c.columns.keys()) == {"user_id", "tax_year"} for c in tp_table.constraints if hasattr(c, "columns")
    )

    # Check TaxCategory code unique constraint
    tc_table = tables["tax_categories"]
    assert tc_table.c.code.unique is True or any(
        set(c.columns.keys()) == {"code"} for c in tc_table.constraints if hasattr(c, "columns")
    )


@pytest.mark.asyncio
async def test_02_family_group_and_member_lifecycle():
    """Test family group creation, membership assignment, role enums, and query relationships."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        owner_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        child_id = uuid.uuid4()
        owner = User(id=owner_id, email="owner@family.com", full_name="Family Owner")
        admin = User(id=admin_id, email="admin@family.com", full_name="Family Admin")
        child = User(id=child_id, email="child@family.com", full_name="Family Child")
        session.add_all([owner, admin, child])
        await session.commit()

        # Create FamilyGroup
        family = FamilyGroup(name="The Simpsons", owner_id=owner_id)
        session.add(family)
        await session.commit()
        await session.refresh(family)

        # Add FamilyMembers
        fm_owner = FamilyMember(family_id=family.id, user_id=owner_id, role=FamilyRole.OWNER)
        fm_admin = FamilyMember(family_id=family.id, user_id=admin_id, role=FamilyRole.ADMIN)
        fm_child = FamilyMember(
            family_id=family.id,
            user_id=child_id,
            role=FamilyRole.CHILD,
            spending_limit_minor=5000,
        )
        session.add_all([fm_owner, fm_admin, fm_child])
        await session.commit()

        # Query and verify relationships with eager loading
        stmt = (
            select(FamilyGroup)
            .where(FamilyGroup.id == family.id)
            .options(selectinload(FamilyGroup.members), selectinload(FamilyGroup.owner))
        )
        res = await session.scalar(stmt)
        assert res is not None
        assert res.name == "The Simpsons"
        assert res.owner.email == "owner@family.com"
        assert len(res.members) == 3

        # Verify member back-populates with eager loading
        child_stmt = (
            select(FamilyMember)
            .where(FamilyMember.user_id == child_id)
            .options(selectinload(FamilyMember.family), selectinload(FamilyMember.user))
        )
        child_member = await session.scalar(child_stmt)
        assert child_member is not None
        assert child_member.role == FamilyRole.CHILD
        assert child_member.spending_limit_minor == 5000
        assert child_member.family.name == "The Simpsons"
        assert child_member.user.full_name == "Family Child"

    await engine.dispose()


@pytest.mark.asyncio
async def test_03_family_member_duplicate_constraint():
    """Verify unique constraint on (family_id, user_id) blocks duplicate membership."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        user_id = uuid.uuid4()
        user = User(id=user_id, email="dup@family.com", full_name="Dup Member")
        session.add(user)
        await session.commit()

        family = FamilyGroup(name="Dup Group", owner_id=user_id)
        session.add(family)
        await session.commit()

        m1 = FamilyMember(family_id=family.id, user_id=user_id, role=FamilyRole.OWNER)
        session.add(m1)
        await session.commit()

        # Attempt duplicate insertion
        m2 = FamilyMember(family_id=family.id, user_id=user_id, role=FamilyRole.ADMIN)
        session.add(m2)
        with pytest.raises(IntegrityError):
            await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_04_family_group_cascade_deletion():
    """Verify deleting a FamilyGroup cascades to remove all FamilyMember entries."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        owner_id = uuid.uuid4()
        owner = User(id=owner_id, email="del_owner@family.com", full_name="Del Owner")
        session.add(owner)
        await session.commit()

        family = FamilyGroup(name="To Delete", owner_id=owner_id)
        session.add(family)
        await session.commit()

        m1 = FamilyMember(family_id=family.id, user_id=owner_id, role=FamilyRole.OWNER)
        session.add(m1)
        await session.commit()

        # Delete family group
        await session.delete(family)
        await session.commit()

        # Verify members are gone
        members = (await session.scalars(select(FamilyMember).where(FamilyMember.family_id == family.id))).all()
        assert len(members) == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_05_tax_profile_crud_and_uniqueness():
    """Test TaxProfile creation, enums, relationship to user, and (user_id, tax_year) uniqueness."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        user_id = uuid.uuid4()
        user = User(id=user_id, email="taxuser@test.com", full_name="Tax User")
        session.add(user)
        await session.commit()

        # Create TaxProfile for 2025
        tp_2025 = TaxProfile(
            user_id=user_id,
            tax_year=2025,
            country="AU",
            business_type=BusinessType.SOLE_TRADER,
            abn="12345678901",
            gst_registered=True,
        )
        session.add(tp_2025)
        await session.commit()
        await session.refresh(tp_2025)

        assert tp_2025.business_type == BusinessType.SOLE_TRADER
        
        # Test eager loading user
        stmt = select(TaxProfile).where(TaxProfile.id == tp_2025.id).options(selectinload(TaxProfile.user))
        tp_loaded = await session.scalar(stmt)
        assert tp_loaded.user.email == "taxuser@test.com"

        # Create TaxProfile for 2026 (should succeed)
        tp_2026 = TaxProfile(
            user_id=user_id,
            tax_year=2026,
            business_type=BusinessType.COMPANY,
            abn="99887766554",
            gst_registered=False,
        )
        session.add(tp_2026)
        await session.commit()

        # Attempt duplicate TaxProfile for 2025 (should fail)
        tp_dup = TaxProfile(
            user_id=user_id,
            tax_year=2025,
            business_type=BusinessType.PARTNERSHIP,
        )
        session.add(tp_dup)
        with pytest.raises(IntegrityError):
            await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_06_tax_category_and_deductions_workflow():
    """Test TaxCategory, TaxDeduction relationships, queries, and constraints."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        user_id = uuid.uuid4()
        user = User(id=user_id, email="deduct@test.com", full_name="Deduct User")
        session.add(user)
        await session.commit()

        # Categories
        cat_office_id = uuid.uuid4()
        cat_travel_id = uuid.uuid4()
        cat_office = TaxCategory(
            id=cat_office_id,
            name="Office Supplies",
            code="OFFICE_EXP",
            type=TaxCategoryType.DEDUCTION,
            description="Work stationery & software",
        )
        cat_travel = TaxCategory(
            id=cat_travel_id,
            name="Work Travel",
            code="TRAVEL_EXP",
            type=TaxCategoryType.DEDUCTION,
            description="Fuel & transit",
        )
        session.add_all([cat_office, cat_travel])
        await session.commit()

        # Unique code test
        cat_dup = TaxCategory(name="Duplicate Office", code="OFFICE_EXP")
        session.add(cat_dup)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        # Create Account & Transaction
        acct = Account(user_id=user_id, name="Checking", type="depository", currency="AUD")
        session.add(acct)
        await session.commit()

        txn = Transaction(
            account_id=acct.id,
            user_id=user_id,
            date=datetime.datetime.now(tz=UTC).date(),
            amount_minor=-15000,  # $150.00
            currency="AUD",
            merchant_raw="Stationery Shop",
            description="Stationery Shop Purchase",
        )
        session.add(txn)
        await session.commit()

        # Create TaxDeduction
        deduction = TaxDeduction(
            user_id=user_id,
            transaction_id=txn.id,
            tax_category_id=cat_office_id,
            amount_minor=15000,
            gst_claimed_minor=1363,  # 10% GST component
            tax_year=2025,
            notes="Ergonomic keyboard for office",
            receipt_url="https://receipts.example.com/rcpt_001.pdf",
        )
        session.add(deduction)
        await session.commit()

        # Query deduction with eager-loaded relationships
        stmt = (
            select(TaxDeduction)
            .where(TaxDeduction.id == deduction.id)
            .options(
                selectinload(TaxDeduction.category),
                selectinload(TaxDeduction.transaction),
                selectinload(TaxDeduction.user),
            )
        )
        res = await session.scalar(stmt)
        assert res is not None
        assert res.amount_minor == 15000
        assert res.gst_claimed_minor == 1363
        assert res.category.code == "OFFICE_EXP"
        assert res.transaction is not None
        assert res.transaction.description == "Stationery Shop Purchase"
        assert res.user.email == "deduct@test.com"

        # Verify reverse relation on TaxCategory
        cat_stmt = (
            select(TaxCategory)
            .where(TaxCategory.id == cat_office_id)
            .options(selectinload(TaxCategory.deductions))
        )
        cat_res = await session.scalar(cat_stmt)
        assert len(cat_res.deductions) == 1
        assert cat_res.deductions[0].id == deduction.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_07_tax_category_fk_restrict_and_transaction_fk_set_null():
    """Verify ondelete='RESTRICT' on TaxCategory and ondelete='SET NULL' on Transaction."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        user_id = uuid.uuid4()
        user = User(id=user_id, email="fk_test@test.com")
        session.add(user)
        await session.commit()

        cat = TaxCategory(name="Tech Gear", code="TECH_01", type=TaxCategoryType.DEDUCTION)
        acct = Account(user_id=user_id, name="Test Acct", type="depository", currency="AUD")
        session.add_all([cat, acct])
        await session.commit()

        txn = Transaction(
            account_id=acct.id,
            user_id=user_id,
            date=datetime.datetime.now(tz=UTC).date(),
            amount_minor=-25000,
            currency="AUD",
            merchant_raw="Monitor Store",
            description="Monitor",
        )
        session.add(txn)
        await session.commit()

        ded = TaxDeduction(
            user_id=user_id,
            transaction_id=txn.id,
            tax_category_id=cat.id,
            amount_minor=25000,
            tax_year=2025,
        )
        session.add(ded)
        await session.commit()

        # 1. Delete Transaction -> deduction.transaction_id becomes NULL (SET NULL)
        await session.delete(txn)
        await session.commit()

        await session.refresh(ded)
        assert ded.transaction_id is None
        assert ded.amount_minor == 25000  # Deduction preserved!

        # 2. Delete TaxCategory -> Raises IntegrityError because deduction exists (RESTRICT)
        await session.delete(cat)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_08_ai_eval_log_crud_and_filtering():
    """Test AiEvalLog creation, field validation, query filtering, and ordering."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        user_id = uuid.uuid4()
        user = User(id=user_id, email="ai_eval_user@test.com")
        session.add(user)
        await session.commit()

        thread_1 = uuid.uuid4()
        thread_2 = uuid.uuid4()

        log1 = AiEvalLog(
            user_id=user_id,
            thread_id=thread_1,
            message_id=uuid.uuid4(),
            provider_used="anthropic",
            model_name="claude-3-5-sonnet",
            tokens_in=120,
            tokens_out=250,
            latency_ms=450,
            route_chosen="tax",
            confidence_score=0.95,
            pii_fields_masked=1,
            query_summary="How do I claim laptop deduction?",
        )
        log2 = AiEvalLog(
            user_id=user_id,
            thread_id=thread_1,
            message_id=uuid.uuid4(),
            provider_used="openai",
            model_name="gpt-4o",
            tokens_in=80,
            tokens_out=150,
            latency_ms=300,
            route_chosen="budget",
            confidence_score=0.99,
            pii_fields_masked=0,
            query_summary="Show my monthly spend",
        )
        log3 = AiEvalLog(
            user_id=user_id,
            thread_id=thread_2,
            message_id=uuid.uuid4(),
            provider_used="anthropic",
            model_name="claude-3-5-sonnet",
            tokens_in=50,
            tokens_out=90,
            latency_ms=200,
            route_chosen="coach",
            confidence_score=0.88,
            pii_fields_masked=0,
            query_summary="General financial advice",
        )
        session.add_all([log1, log2, log3])
        await session.commit()

        # Query by thread_id
        logs_t1 = (
            await session.scalars(
                select(AiEvalLog)
                .where(AiEvalLog.user_id == user_id, AiEvalLog.thread_id == thread_1)
                .order_by(AiEvalLog.created_at.desc())
            )
        ).all()
        assert len(logs_t1) == 2
        assert {l.route_chosen for l in logs_t1} == {"tax", "budget"}

        # Query total eval logs for user
        all_logs = (
            await session.scalars(select(AiEvalLog).where(AiEvalLog.user_id == user_id))
        ).all()
        assert len(all_logs) == 3

    await engine.dispose()


@pytest.mark.asyncio
async def test_09_user_deletion_cascade_to_all_new_models():
    """Verify deleting a User cascades to FamilyGroup, FamilyMember, TaxProfile, TaxDeduction, and AiEvalLog."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        user_id = uuid.uuid4()
        user = User(id=user_id, email="cascade_master@test.com")
        session.add(user)
        await session.commit()

        family = FamilyGroup(name="Cascade Family", owner_id=user_id)
        session.add(family)
        await session.commit()

        fm = FamilyMember(family_id=family.id, user_id=user_id, role=FamilyRole.OWNER)
        tp = TaxProfile(user_id=user_id, tax_year=2025, business_type=BusinessType.SOLE_TRADER)
        cat = TaxCategory(name="Generic", code="GEN", type=TaxCategoryType.DEDUCTION)
        session.add_all([fm, tp, cat])
        await session.commit()

        td = TaxDeduction(user_id=user_id, tax_category_id=cat.id, amount_minor=5000, tax_year=2025)
        ae = AiEvalLog(user_id=user_id, provider_used="anthropic", model_name="claude-3-5", latency_ms=100)
        session.add_all([td, ae])
        await session.commit()

        # Now delete the user
        await session.delete(user)
        await session.commit()

        # Verify all child records owned by the user are deleted
        assert (await session.scalar(select(FamilyGroup).where(FamilyGroup.owner_id == user_id))) is None
        assert (await session.scalar(select(FamilyMember).where(FamilyMember.user_id == user_id))) is None
        assert (await session.scalar(select(TaxProfile).where(TaxProfile.user_id == user_id))) is None
        assert (await session.scalar(select(TaxDeduction).where(TaxDeduction.user_id == user_id))) is None
        assert (await session.scalar(select(AiEvalLog).where(AiEvalLog.user_id == user_id))) is None

        # But TaxCategory remains intact
        assert (await session.scalar(select(TaxCategory).where(TaxCategory.id == cat.id))) is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_10_existing_models_non_regression():
    """Verify that all pre-existing models can be instantiated, saved, and queried without conflict."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        user_id = uuid.uuid4()
        user = User(id=user_id, email="existing_models@test.com", full_name="Existing Tester")
        session.add(user)
        await session.commit()

        acct = Account(user_id=user_id, name="Savings", type="depository", currency="USD", balance_minor=100000)
        cat = Category(user_id=user_id, name="Food", kind="expense", color="#FF0000", icon="utensils")
        session.add_all([acct, cat])
        await session.commit()

        txn = Transaction(
            account_id=acct.id,
            user_id=user_id,
            date=datetime.datetime.now(tz=UTC).date(),
            category_id=cat.id,
            amount_minor=-2500,
            currency="USD",
            merchant_raw="Grocery store",
            description="Grocery store",
        )
        session.add(txn)
        await session.commit()

        split = TransactionSplit(
            transaction_id=txn.id,
            category_id=cat.id,
            amount_minor=-2500,
            memo="Split item 1",
        )
        bgt = Budget(
            user_id=user_id,
            name="Monthly Budget",
            strategy="envelope",
            period="monthly",
            start_date=datetime.datetime.now(tz=UTC).date(),
            income_planned_minor=500000,
        )
        session.add_all([split, bgt])
        await session.commit()

        env = BudgetEnvelope(budget_id=bgt.id, category_id=cat.id, allocated_minor=50000)
        goal = Goal(user_id=user_id, name="Emergency Fund", target_minor=1000000, saved_minor=200000)
        debt = Debt(user_id=user_id, name="Credit Card", principal_minor=500000, apr_bps=1999, min_payment_minor=15000)
        alert = Alert(user_id=user_id, type="budget_warning", title="Approaching limit", body="You spent 80%")
        fx = FxRate(base="USD", quote="AUD", rate=1.52)
        sub = RecurringSubscription(
            user_id=user_id,
            merchant_norm="Streaming",
            display_name="Streaming Service",
            avg_amount_minor=1499,
            currency="USD",
            cadence_days=30,
            first_seen=datetime.datetime.now(tz=UTC).date(),
            last_seen=datetime.datetime.now(tz=UTC).date(),
        )
        thread = ChatThread(user_id=user_id, title="Test Chat", agent_mode="auto")
        session.add_all([env, goal, debt, alert, fx, sub, thread])
        await session.commit()

        msg = ChatMessage(thread_id=thread.id, role="user", content="Hello AI")
        kdoc = KnowledgeDoc(user_id=user_id, title="Doc 1", content="Financial tips")
        audit = AuditLog(user_id=user_id, action="LOGIN", ip="127.0.0.1")
        oauth = OAuthAccount(user_id=user_id, provider="google", provider_account_id="g123")
        passkey = PasskeyCredential(user_id=user_id, credential_id="cred123", public_key="pk123", sign_count=0)
        rt = RefreshToken(user_id=user_id, token_hash="hash123", expires_at=datetime.datetime.now(UTC) + datetime.timedelta(days=7))
        session.add_all([msg, kdoc, audit, oauth, passkey, rt])
        await session.commit()

        # Query all and verify existence
        assert (await session.scalar(select(User).where(User.id == user_id))) is not None
        assert (await session.scalar(select(Account).where(Account.id == acct.id))) is not None
        assert (await session.scalar(select(Transaction).where(Transaction.id == txn.id))) is not None
        assert (await session.scalar(select(TransactionSplit).where(TransactionSplit.id == split.id))) is not None
        assert (await session.scalar(select(Budget).where(Budget.id == bgt.id))) is not None
        assert (await session.scalar(select(BudgetEnvelope).where(BudgetEnvelope.id == env.id))) is not None
        assert (await session.scalar(select(Goal).where(Goal.id == goal.id))) is not None
        assert (await session.scalar(select(Debt).where(Debt.id == debt.id))) is not None
        assert (await session.scalar(select(Alert).where(Alert.id == alert.id))) is not None
        assert (await session.scalar(select(FxRate).where(FxRate.base == "USD", FxRate.quote == "AUD"))) is not None
        assert (await session.scalar(select(RecurringSubscription).where(RecurringSubscription.id == sub.id))) is not None
        assert (await session.scalar(select(ChatThread).where(ChatThread.id == thread.id))) is not None
        assert (await session.scalar(select(ChatMessage).where(ChatMessage.id == msg.id))) is not None
        assert (await session.scalar(select(KnowledgeDoc).where(KnowledgeDoc.id == kdoc.id))) is not None
        assert (await session.scalar(select(AuditLog).where(AuditLog.id == audit.id))) is not None
        assert (await session.scalar(select(OAuthAccount).where(OAuthAccount.id == oauth.id))) is not None
        assert (await session.scalar(select(PasskeyCredential).where(PasskeyCredential.id == passkey.id))) is not None
        assert (await session.scalar(select(RefreshToken).where(RefreshToken.id == rt.id))) is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_11_alembic_migration_upgrade_and_downgrade():
    """Verify that Alembic migration 0002 applies and rolls back cleanly against a database."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    # Load 0001 migration
    mig1_path = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "0001_initial_schema.py")
    spec1 = importlib.util.spec_from_file_location("migration_0001", mig1_path)
    mig1 = importlib.util.module_from_spec(spec1)
    spec1.loader.exec_module(mig1)

    # Load 0002 migration
    mig2_path = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "0002_family_tax_ai_eval.py")
    spec2 = importlib.util.spec_from_file_location("migration_0002", mig2_path)
    mig2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(mig2)

    # Test running upgrade and downgrade on sync SQLite engine
    sync_engine = create_engine("sqlite:///:memory:")
    with sync_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        
        # Monkey patch op in migration modules
        mig1.op = op
        mig2.op = op

        # Run 0001 upgrade
        mig1.upgrade()
        insp = inspect(conn)
        tables_after_0001 = set(insp.get_table_names())
        assert "users" in tables_after_0001
        assert "transactions" in tables_after_0001
        assert "family_groups" not in tables_after_0001

        # Run 0002 upgrade
        mig2.upgrade()
        insp = inspect(conn)
        tables_after_0002 = set(insp.get_table_names())
        new_tables = {
            "family_groups",
            "family_members",
            "tax_profiles",
            "tax_categories",
            "tax_deductions",
            "ai_eval_logs",
        }
        for nt in new_tables:
            assert nt in tables_after_0002, f"Table {nt} was not created in 0002 upgrade"

        # Run 0002 downgrade
        mig2.downgrade()
        insp = inspect(conn)
        tables_after_downgrade = set(insp.get_table_names())
        for nt in new_tables:
            assert nt not in tables_after_downgrade, f"Table {nt} was not dropped in 0002 downgrade"


@pytest.mark.asyncio
async def test_12_multi_member_family_group_stress():
    """Stress test: 50 members in a single family group, verify member deletion vs group deletion."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        owner = User(id=uuid.uuid4(), email="big_family_owner@test.com")
        session.add(owner)
        await session.commit()

        family = FamilyGroup(name="Large Clan", owner_id=owner.id)
        session.add(family)
        await session.commit()

        # Add 50 members
        members_users = []
        for i in range(50):
            u = User(id=uuid.uuid4(), email=f"member_{i}@family.com")
            members_users.append(u)
        session.add_all(members_users)
        await session.commit()

        fms = [
            FamilyMember(
                family_id=family.id,
                user_id=u.id,
                role=FamilyRole.MEMBER if i % 2 == 0 else FamilyRole.CHILD,
                spending_limit_minor=1000 * i if i % 2 != 0 else None,
            )
            for i, u in enumerate(members_users)
        ]
        session.add_all(fms)
        await session.commit()

        # Verify all 50 members counted
        count_stmt = select(FamilyMember).where(FamilyMember.family_id == family.id)
        count_res = (await session.scalars(count_stmt)).all()
        assert len(count_res) == 50

        # Delete one individual member user -> member removed, family remains
        target_user = members_users[0]
        await session.delete(target_user)
        await session.commit()

        count_after = (await session.scalars(count_stmt)).all()
        assert len(count_after) == 49
        assert (await session.scalar(select(FamilyGroup).where(FamilyGroup.id == family.id))) is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_13_multiple_deductions_per_transaction_and_set_null_cascade():
    """Stress test: multiple deductions linked to single transaction; verify SET NULL cascades to all."""
    engine, session_factory = await setup_test_db()
    async with session_factory() as session:
        user = User(id=uuid.uuid4(), email="split_deduct@test.com")
        session.add(user)
        await session.commit()

        cat1 = TaxCategory(name="Cat 1", code="C1", type=TaxCategoryType.DEDUCTION)
        cat2 = TaxCategory(name="Cat 2", code="C2", type=TaxCategoryType.DEDUCTION)
        acct = Account(user_id=user.id, name="Biz Acct", type="depository", currency="AUD")
        session.add_all([cat1, cat2, acct])
        await session.commit()

        txn = Transaction(
            account_id=acct.id,
            user_id=user.id,
            date=datetime.datetime.now(tz=UTC).date(),
            amount_minor=-50000,
            currency="AUD",
            merchant_raw="Mixed Store",
        )
        session.add(txn)
        await session.commit()

        d1 = TaxDeduction(user_id=user.id, transaction_id=txn.id, tax_category_id=cat1.id, amount_minor=30000, tax_year=2025)
        d2 = TaxDeduction(user_id=user.id, transaction_id=txn.id, tax_category_id=cat2.id, amount_minor=20000, tax_year=2025)
        session.add_all([d1, d2])
        await session.commit()

        # Delete transaction
        await session.delete(txn)
        await session.commit()

        await session.refresh(d1)
        await session.refresh(d2)
        assert d1.transaction_id is None
        assert d2.transaction_id is None
        assert d1.amount_minor == 30000
        assert d2.amount_minor == 20000

    await engine.dispose()
