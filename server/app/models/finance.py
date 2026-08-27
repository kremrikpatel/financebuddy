"""Core finance models: connections, accounts, transactions, categories."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow


class BankConnection(UUIDMixin, TimestampMixin, Base):
    """A link to an aggregation provider (Plaid / GoCardless / Basiq)."""

    __tablename__ = "bank_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30))  # plaid|gocardless|basiq|manual
    region: Mapped[str | None] = mapped_column(String(10))  # US|EU|UK|AU
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)  # item id / requisition id
    access_token_sealed: Mapped[str | None] = mapped_column(Text)
    institution_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|revoked|error


class Account(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bank_connections.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(30), default="depository")  # depository|credit|loan|investment|cash
    subtype: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    balance_minor: Mapped[int] = mapped_column(BigInteger, default=0)  # positive = assets; credit debt stored negative
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("user_id", "external_id", name="uq_account_external"),)


class Category(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)  # NULL => system category
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="expense")  # expense|income|transfer|savings
    color: Mapped[str] = mapped_column(String(9), default="#6366f1")
    icon: Mapped[str] = mapped_column(String(50), default="wallet")

    __table_args__ = (Index("ix_cat_user_name", "user_id", "name", unique=True),)


class Transaction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "transactions"

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)  # signed; expense negative, income positive
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    merchant_raw: Mapped[str] = mapped_column(Text)
    merchant_norm: Mapped[str] = mapped_column(Text, default="", index=True)
    description: Mapped[str | None] = mapped_column(Text)
    notes_encrypted: Mapped[str | None] = mapped_column(Text)  # E2E ciphertext from client vault

    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    tags: Mapped[list | None] = mapped_column(JSON, default=list)

    source: Mapped[str] = mapped_column(String(20), default="sync")  # sync|csv|ofx|receipt|manual|api
    external_id: Mapped[str | None] = mapped_column(String(255))
    import_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    pending: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)  # transfers/ignored
    is_income: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    categorization_method: Mapped[str | None] = mapped_column(String(20))  # rule|knn|llm|user|seed
    categorization_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    embedding: Mapped[list | None] = mapped_column(Vector(settings.embedding_dim))

    # splits
    is_split_parent: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)

    receipt_url: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("account_id", "external_id", name="uq_txn_external"),
        Index("ix_txn_user_date", "user_id", "date"),
    )


class TransactionSplit(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "transaction_splits"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    memo: Mapped[str | None] = mapped_column(Text)


class RecurringSubscription(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "recurring_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    merchant_norm: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200))
    avg_amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    cadence_days: Mapped[int] = mapped_column(Integer)
    first_seen: Mapped[date] = mapped_column(Date)
    last_seen: Mapped[date] = mapped_column(Date)
    next_expected: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|cancelled|duplicate
    duplicates_of_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    last_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
