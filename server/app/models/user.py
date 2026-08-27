"""Identity, auth and zero-knowledge vault models."""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(256))
    full_name: Mapped[str | None] = mapped_column(String(200))
    locale: Mapped[str] = mapped_column(String(10), default="en")
    base_currency: Mapped[str] = mapped_column(String(3), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

    # MFA (TOTP secret stored sealed)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret_sealed: Mapped[str | None] = mapped_column(Text)
    recovery_codes: Mapped[list | None] = mapped_column(JSON, default=list)

    # Zero-knowledge vault (server never sees plaintext key material)
    vault_salt: Mapped[str | None] = mapped_column(String(64))
    vault_wrapped_dek: Mapped[str | None] = mapped_column(Text)
    vault_verifier: Mapped[str | None] = mapped_column(String(128))
    vault_algo: Mapped[str | None] = mapped_column(String(32))


class RefreshToken(UUIDMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device: Mapped[str | None] = mapped_column(String(200))
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasskeyCredential(UUIDMixin, TimestampMixin, Base):
    """WebAuthn credential — biometric/platform authenticator login."""

    __tablename__ = "passkey_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    transports: Mapped[list | None] = mapped_column(JSON, default=list)
    device_type: Mapped[str | None] = mapped_column(String(100))
    label: Mapped[str | None] = mapped_column(String(100))


class OAuthAccount(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "oauth_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    provider_account_id: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))

    __table_args__ = (Index("ix_oauth_provider_account", "provider", "provider_account_id", unique=True),)


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
