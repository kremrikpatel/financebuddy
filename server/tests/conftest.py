"""Pytest fixtures for FinanceBuddy backend testing."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from pgvector.sqlalchemy import Vector
from sqlalchemy import StaticPool, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.security import create_access_token, hash_password, new_refresh_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Account, Category, FxRate, RefreshToken, User
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

    # Filter out postgresql-specific indexes for SQLite table creation
    async with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            for idx in list(table.indexes):
                if hasattr(idx, "dialect_kwargs") and "postgresql_using" in idx.dialect_kwargs:
                    pass
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        # Ensure system categories exist in the session
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
async def auth_headers(test_user: User) -> dict[str, str]:
    token = create_access_token(test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_tokens(db_session: AsyncSession, test_user: User) -> dict[str, str]:
    """Provide valid access and refresh tokens for test_user."""
    access_token = create_access_token(test_user.id)
    raw_refresh, token_hash = new_refresh_token()
    rt = RefreshToken(
        user_id=test_user.id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        revoked=False,
    )
    db_session.add(rt)
    await db_session.commit()
    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "user_id": str(test_user.id),
        "Authorization": f"Bearer {access_token}",
    }


@pytest.fixture
async def test_account(db_session: AsyncSession, test_user: User) -> Account:
    """Provide a default active depository checking account for test_user."""
    account = Account(
        user_id=test_user.id,
        name="Main Everyday Checking",
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
