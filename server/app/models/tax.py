"""Tax management models: Tax profiles, categories, and deductions."""
from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.finance import Transaction
    from app.models.user import User


class BusinessType(str, enum.Enum):
    SOLE_TRADER = "sole_trader"
    COMPANY = "company"
    PARTNERSHIP = "partnership"


class TaxCategoryType(str, enum.Enum):
    DEDUCTION = "deduction"
    INCOME = "income"
    GST_CLAIMABLE = "gst_claimable"


class TaxProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tax_year: Mapped[int] = mapped_column(Integer, index=True)
    country: Mapped[str] = mapped_column(String(10), default="AU")
    business_type: Mapped[BusinessType] = mapped_column(
        String(30), default=BusinessType.SOLE_TRADER
    )
    abn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gst_registered: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("user_id", "tax_year", name="uq_tax_profile_user_year"),
        Index("ix_tax_profile_user_year", "user_id", "tax_year"),
    )


class TaxCategory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_categories"

    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    type: Mapped[TaxCategoryType] = mapped_column(
        String(30), default=TaxCategoryType.DEDUCTION
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    deductions: Mapped[list[TaxDeduction]] = relationship(
        "TaxDeduction", back_populates="category"
    )


class TaxDeduction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_deductions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tax_category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax_categories.id", ondelete="RESTRICT"), index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    gst_claimed_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    tax_year: Mapped[int] = mapped_column(Integer, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])
    transaction: Mapped[Transaction | None] = relationship(
        "Transaction", foreign_keys=[transaction_id]
    )
    category: Mapped[TaxCategory] = relationship(
        "TaxCategory", foreign_keys=[tax_category_id], back_populates="deductions"
    )

    __table_args__ = (
        Index("ix_tax_deductions_user_year", "user_id", "tax_year"),
    )