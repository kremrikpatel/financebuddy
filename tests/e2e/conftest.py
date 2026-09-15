"""Pytest fixtures for FinanceBuddy Feature Expansion E2E testing."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from pgvector.sqlalchemy import Vector
from sqlalchemy import StaticPool, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

# Add server directory to sys.path if not present
server_dir = Path(__file__).resolve().parent.parent.parent / "server"
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from app.core.security import create_access_token, hash_password, new_refresh_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Account,
    Category,
    FxRate,
    RefreshToken,
    User,
)
from app.models.family import FamilyGroup, FamilyMember, FamilyRole
from app.models.tax import (
    BusinessType,
    TaxCategory,
    TaxCategoryType,
    TaxDeduction,
    TaxProfile,
)
from app.models.ai import AiEvalLog, ChatMessage, ChatThread
from app.seed import INITIAL_FX_RATES, SYSTEM_CATEGORIES


# Compile Vector type as TEXT on SQLite
@compiles(Vector, "sqlite")
def compile_vector_sqlite(type_, compiler, **kw):
    return "TEXT"


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        # Ensure system categories exist
        for item in SYSTEM_CATEGORIES:
            name, kind, color = item[0], item[1], item[2]
            icon = item[3] if len(item) > 3 else "wallet"
            existing = await session.scalar(
                select(Category).where(Category.name == name, Category.user_id.is_(None))
            )
            if not existing:
                session.add(Category(user_id=None, name=name, kind=kind, color=color, icon=icon))

        # Ensure baseline FX rates exist
        for base_c, quote_c, rate in INITIAL_FX_RATES:
            existing_fx = await session.scalar(
                select(FxRate).where(FxRate.base == base_c, FxRate.quote == quote_c)
            )
            if not existing_fx:
                session.add(FxRate(base=base_c, quote=quote_c, rate=rate))

        # Seed Standard AU Tax Categories
        standard_tax_categories = [
            ("Work-Related Car Expenses", "D1_CAR", TaxCategoryType.DEDUCTION, "Vehicle expenses for business travel"),
            ("Home Office Expenses", "D2_HOME_OFFICE", TaxCategoryType.DEDUCTION, "Electricity, internet, office furniture"),
            ("Self-Education Expenses", "D3_EDUCATION", TaxCategoryType.DEDUCTION, "Courses and certifications"),
            ("Tools and Equipment", "D4_TOOLS", TaxCategoryType.DEDUCTION, "Computers, phones, instruments under $300 or depreciated"),
            ("Other Work Deductions", "D5_OTHER", TaxCategoryType.DEDUCTION, "Union fees, professional subscriptions"),
            ("Business Revenue", "INCOME_BIZ", TaxCategoryType.INCOME, "Gross trading and service income"),
            ("GST on Sales (1A)", "GST_1A", TaxCategoryType.GST_CLAIMABLE, "GST collected from customers"),
            ("GST on Purchases (1B)", "GST_1B", TaxCategoryType.GST_CLAIMABLE, "GST credits paid on business expenses"),
        ]
        for name, code, cat_type, desc in standard_tax_categories:
            existing_cat = await session.scalar(
                select(TaxCategory).where(TaxCategory.code == code)
            )
            if not existing_cat:
                session.add(TaxCategory(name=name, code=code, type=cat_type, description=desc))

        await session.commit()
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def async_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """Alias for client fixture for E2E tests."""
    yield client


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = await db_session.scalar(select(User).where(User.email == "testuser@example.com"))
    if not user:
        user = User(
            email="testuser@example.com",
            password_hash=hash_password("TestPass123!"),
            full_name="Test User",
            locale="en",
            base_currency="USD",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
    return user


@pytest.fixture
async def family_owner_user(db_session: AsyncSession) -> User:
    user = await db_session.scalar(select(User).where(User.email == "family_owner@example.com"))
    if not user:
        user = User(
            email="family_owner@example.com",
            password_hash=hash_password("OwnerPass123!"),
            full_name="Family Owner",
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
    return user


@pytest.fixture
async def family_admin_user(db_session: AsyncSession) -> User:
    user = await db_session.scalar(select(User).where(User.email == "family_admin@example.com"))
    if not user:
        user = User(
            email="family_admin@example.com",
            password_hash=hash_password("AdminPass123!"),
            full_name="Family Admin",
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
    return user


@pytest.fixture
async def family_child_user(db_session: AsyncSession) -> User:
    user = await db_session.scalar(select(User).where(User.email == "family_child@example.com"))
    if not user:
        user = User(
            email="family_child@example.com",
            password_hash=hash_password("ChildPass123!"),
            full_name="Family Child",
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
    return user


@pytest.fixture
async def sole_trader_user(db_session: AsyncSession) -> User:
    user = await db_session.scalar(select(User).where(User.email == "sole_trader@example.com"))
    if not user:
        user = User(
            email="sole_trader@example.com",
            password_hash=hash_password("TraderPass123!"),
            full_name="Alex SoleTrader",
            locale="en",
            base_currency="AUD",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
    return user


@pytest.fixture
async def auth_headers(test_user: User) -> dict[str, str]:
    token = create_access_token(test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def owner_headers(family_owner_user: User) -> dict[str, str]:
    token = create_access_token(family_owner_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_headers(family_admin_user: User) -> dict[str, str]:
    token = create_access_token(family_admin_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def child_headers(family_child_user: User) -> dict[str, str]:
    token = create_access_token(family_child_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def sole_trader_headers(sole_trader_user: User) -> dict[str, str]:
    token = create_access_token(sole_trader_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_account(db_session: AsyncSession, test_user: User) -> Account:
    account = await db_session.scalar(
        select(Account).where(Account.user_id == test_user.id, Account.name == "Everyday Checking")
    )
    if not account:
        account = Account(
            user_id=test_user.id,
            name="Everyday Checking",
            type="depository",
            subtype="checking",
            currency="USD",
            balance_minor=500000,
            is_manual=True,
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)
    return account


@pytest.fixture
async def au_business_account(db_session: AsyncSession, sole_trader_user: User) -> Account:
    account = await db_session.scalar(
        select(Account).where(
            Account.user_id == sole_trader_user.id, Account.name == "CommBank Business Account"
        )
    )
    if not account:
        account = Account(
            user_id=sole_trader_user.id,
            name="CommBank Business Account",
            type="depository",
            subtype="checking",
            currency="AUD",
            balance_minor=1200000,
            is_manual=True,
        )
        db_session.add(account)
        await db_session.commit()
        await db_session.refresh(account)
    return account
