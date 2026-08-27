"""Budgets, goals, debts, alerts."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class Budget(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "budgets"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(120))
    strategy: Mapped[str] = mapped_column(String(20), default="envelope")  # envelope|zero_based|traditional
    period: Mapped[str] = mapped_column(String(20), default="monthly")
    start_date: Mapped[date] = mapped_column(Date)
    income_planned_minor: Mapped[int] = mapped_column(BigInteger, default=0)  # zero-based target
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class BudgetEnvelope(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "budget_envelopes"

    budget_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("budgets.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    allocated_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    rollover: Mapped[bool] = mapped_column(Boolean, default=False)
    carry_in_minor: Mapped[int] = mapped_column(BigInteger, default=0)


class Goal(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "goals"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(200))
    target_minor: Mapped[int] = mapped_column(BigInteger)
    saved_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    target_date: Mapped[date | None] = mapped_column(Date)
    strategy: Mapped[str] = mapped_column(String(30), default="fixed_monthly")
    # fixed_monthly | percent_income | round_up
    monthly_amount_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    percent_of_income: Mapped[float] = mapped_column(Float, default=0.0)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Debt(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "debts"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(200))
    principal_minor: Mapped[int] = mapped_column(BigInteger)  # remaining balance (positive)
    apr_bps: Mapped[int] = mapped_column(Integer, default=0)  # APR in basis points
    min_payment_minor: Mapped[int] = mapped_column(BigInteger)
    due_day: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    paid_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Alert(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "alerts"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    type: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info|warning|critical
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_alert_user_unread", "user_id", "read_at"),)


class FxRate(TimestampMixin, Base):
    __tablename__ = "fx_rates"

    base: Mapped[str] = mapped_column(String(3), primary_key=True)
    quote: Mapped[str] = mapped_column(String(3), primary_key=True)
    rate: Mapped[float] = mapped_column(Float)
