"""Family profiles and household sharing models."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow

if TYPE_CHECKING:
    from app.models.user import User


class FamilyRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    CHILD = "child"


class FamilyGroup(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "family_groups"

    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Relationships
    owner: Mapped[User] = relationship("User", foreign_keys=[owner_id])
    members: Mapped[list[FamilyMember]] = relationship(
        "FamilyMember", back_populates="family", cascade="all, delete-orphan"
    )


class FamilyMember(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "family_members"

    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_groups.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[FamilyRole] = mapped_column(
        String(20), default=FamilyRole.MEMBER
    )
    spending_limit_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    family: Mapped[FamilyGroup] = relationship("FamilyGroup", back_populates="members")
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("family_id", "user_id", name="uq_family_member"),
    )