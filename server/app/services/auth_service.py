"""Authentication service: registration, login, refresh rotation,
TOTP MFA, WebAuthn passkeys, zero-knowledge vault registration."""
from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import webauthn
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import seal
from app.core.logging import get_logger
from app.core.security import (
    constant_time_eq,
    create_access_token,
    generate_recovery_codes,
    hash_password,
    new_refresh_token,
    verify_password,
)
from app.models import AuditLog, OAuthAccount, PasskeyCredential, RefreshToken, User

log = get_logger("auth")


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


# ── Core flows ──────────────────────────────────────────────────────────

async def register(db: AsyncSession, email: str, password: str, full_name: str | None,
                   locale: str = "en", base_currency: str = "USD") -> User:
    existing = await db.scalar(select(User).where(User.email == email.lower()))
    if existing:
        raise AuthError("Email already registered", 409)
    user = User(email=email.lower(), password_hash=hash_password(password),
                full_name=full_name, locale=locale, base_currency=base_currency.upper())
    db.add(user)
    await db.flush()
    return user


async def issue_tokens(db: AsyncSession, user: User, device: str | None = None,
                       mfa_required: bool = False) -> tuple[str, str]:
    access = create_access_token(user.id, {"mfa": not mfa_required})
    raw, token_hash = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, device=device,
                        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days)))
    await _prune_sessions(db, user.id)
    return access, raw


async def rotate_refresh(db: AsyncSession, raw_token: str, device: str | None = None) -> tuple[User, str, str]:
    from app.core.security import _sha256

    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _sha256(raw_token)))
    if not row or row.revoked_at or row.expires_at < datetime.now(UTC):
        raise AuthError("Invalid refresh token", 401)
    row.revoked_at = datetime.now(UTC)
    user = await db.get(User, row.user_id)
    if not user or not user.is_active:
        raise AuthError("User inactive", 401)
    access, fresh = await issue_tokens(db, user, device)
    return user, access, fresh


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))


async def _prune_sessions(db: AsyncSession, user_id: uuid.UUID, keep: int = 10) -> None:
    rows = (await db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user_id)
        .order_by(RefreshToken.created_at.desc())
    )).scalars().all()
    for stale in rows[keep:]:
        await db.delete(stale)


# ── Login w/ MFA ────────────────────────────────────────────────────────

async def authenticate(db: AsyncSession, email: str, password: str,
                       totp_code: str | None, recovery_code: str | None) -> tuple[User, bool]:
    """Returns (user, mfa_satisfied)."""
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise AuthError("Invalid credentials", 401)
    if not user.mfa_enabled:
        return user, True
    if totp_code and _check_totp(user, totp_code):
        return user, True
    if recovery_code:
        codes = user.recovery_codes or []
        normalized = recovery_code.strip().upper()
        for c in codes:
            if constant_time_eq(c, normalized):
                codes.remove(c)
                flag_modified(user, "recovery_codes")
                return user, True
    return user, False


def _check_totp(user: User, code: str) -> bool:
    if not user.mfa_secret_sealed:
        return False
    from app.core.crypto import open_sealed

    secret = open_sealed(user.mfa_secret_sealed)
    return pyotp.TOTP(secret).verify(code.replace(" ", ""), valid_window=1)


def flag_modified(instance, attr):  # small local helper to avoid extra import noise
    from sqlalchemy.orm.attributes import flag_modified as fm

    fm(instance, attr)


async def enable_mfa_start(db: AsyncSession, user: User) -> tuple[str, str]:
    secret = pyotp.random_base32()
    user.mfa_secret_sealed = seal(secret)
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="FinanceBuddy")
    return secret, uri


async def enable_mfa_confirm(db: AsyncSession, user: User, code: str) -> list[str]:
    if not user.mfa_secret_sealed:
        raise AuthError("Start MFA enrollment first")
    if not _check_totp(user, code):
        raise AuthError("Invalid code", 401)
    user.mfa_enabled = True
    codes = generate_recovery_codes()
    user.recovery_codes = codes
    return codes


async def disable_mfa(db: AsyncSession, user: User, code: str) -> None:
    if not _check_totp(user, code):
        raise AuthError("Invalid code", 401)
    user.mfa_enabled = False
    user.mfa_secret_sealed = None
    user.recovery_codes = []


# ── Vault (zero-knowledge) ──────────────────────────────────────────────

async def vault_setup(db: AsyncSession, user: User, payload: dict) -> None:
    user.vault_algo = payload["kdf"]
    user.vault_salt = payload["kdf_salt_hex"]
    user.vault_wrapped_dek = payload["wrapped_dek_b64"]
    user.vault_verifier = payload["verifier_b64"]


# ── Passkeys / biometrics ───────────────────────────────────────────────

_RP_NAME = "FinanceBuddy"


def _rp_parts(origin: str) -> tuple[str, str]:
    from urllib.parse import urlparse

    p = urlparse(origin)
    return p.hostname or "localhost", origin


def _expected_origins(origin: str | None = None) -> list[str]:
    origins = set()
    for o in settings.cors_origin_list:
        if not o.startswith("[") and o.strip():
            origins.add(o.strip().rstrip("/"))
    if origin:
        origins.add(origin.rstrip("/"))
    # Common local dev origins
    origins.add("http://localhost:5173")
    origins.add("http://localhost:8000")
    origins.add("http://127.0.0.1:5173")
    origins.add("http://127.0.0.1:8000")
    origins.add("tauri://localhost")
    origins.add("http://tauri.localhost")
    return list(origins)


def passkey_register_options(user: User, origin: str) -> dict:
    rp_id, _ = _rp_parts(origin)
    opts = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=_RP_NAME,
        user_id=str(user.id).encode("utf-8"),
        user_name=user.email,
        user_display_name=user.full_name or user.email,
    )
    return json.loads(webauthn.options_to_json(opts))


async def passkey_register_finish(db: AsyncSession, user: User, credential: dict,
                                  challenge: bytes, label: str | None, origin: str) -> PasskeyCredential:
    rp_id, _ = _rp_parts(origin)
    try:
        verification = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_origin=_expected_origins(origin),
            expected_rp_id=rp_id,
            require_user_verification=False,
        )
    except Exception as exc:
        raise AuthError(f"Passkey registration verification failed: {exc}", 400) from exc

    cred_id_b64 = base64.urlsafe_b64encode(verification.credential_id).decode()
    pub_key_b64 = base64.urlsafe_b64encode(verification.credential_public_key).decode()

    cred = PasskeyCredential(
        user_id=user.id,
        credential_id=cred_id_b64,
        public_key=pub_key_b64,
        sign_count=verification.sign_count,
        device_type=verification.credential_device_type,
        label=label or "Passkey",
    )
    db.add(cred)
    return cred


def passkey_auth_options(credentials: list[PasskeyCredential], origin: str) -> dict:
    rp_id, _ = _rp_parts(origin)
    descriptors = []
    for c in credentials:
        try:
            pad = "=" * (-len(c.credential_id) % 4)
            cid = base64.urlsafe_b64decode(c.credential_id + pad)
            descriptors.append(webauthn.helpers.structs.PublicKeyCredentialDescriptor(id=cid))
        except Exception:
            continue
    opts = webauthn.generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=descriptors if descriptors else None,
    )
    return json.loads(webauthn.options_to_json(opts))


async def passkey_auth_finish(db: AsyncSession, credential: dict, challenge: bytes,
                              credential_id_b64: str, origin: str) -> PasskeyCredential:
    """Verify assertion against a previously looked-up stored credential."""
    rp_id, _ = _rp_parts(origin)
    stored = await db.scalar(
        select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id_b64)
    )
    if not stored:
        # Try raw credential id from dictionary
        raw_id = credential.get("id") or credential.get("rawId")
        if raw_id:
            pad = "=" * (-len(raw_id) % 4)
            normalized = base64.urlsafe_b64encode(base64.urlsafe_b64decode(raw_id + pad)).decode()
            stored = await db.scalar(
                select(PasskeyCredential).where(PasskeyCredential.credential_id == normalized)
            )
    if not stored:
        raise AuthError("Unknown passkey credential", 401)

    try:
        pub_key_pad = "=" * (-len(stored.public_key) % 4)
        pub_key_bytes = base64.urlsafe_b64decode(stored.public_key + pub_key_pad)
        verification = webauthn.verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_origin=_expected_origins(origin),
            expected_rp_id=rp_id,
            credential_public_key=pub_key_bytes,
            credential_current_sign_count=stored.sign_count,
            require_user_verification=False,
        )
    except Exception as exc:
        raise AuthError(f"Passkey authentication verification failed: {exc}", 401) from exc

    stored.sign_count = verification.new_sign_count
    return stored


# ── Social OAuth (authorization-code scaffolding) ───────────────────────

async def upsert_oauth_user(db: AsyncSession, provider: str, provider_account_id: str,
                            email: str, name: str | None) -> User:
    link = await db.scalar(select(OAuthAccount).where(
        OAuthAccount.provider == provider, OAuthAccount.provider_account_id == provider_account_id))
    if link:
        user = await db.get(User, link.user_id)
        if not user:
            raise AuthError("Linked account missing", 401)
        return user
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if not user:
        user = User(email=email.lower(), full_name=name)
        db.add(user)
        await db.flush()
    db.add(OAuthAccount(user_id=user.id, provider=provider,
                        provider_account_id=provider_account_id, email=email))
    return user


async def audit(db: AsyncSession, action: str, user_id: uuid.UUID | None,
                ip: str | None = None, ua: str | None = None, detail: dict | None = None) -> None:
    db.add(AuditLog(user_id=user_id, action=action, ip=ip, user_agent=ua, detail=detail))
    log.info("audit", action=action, user=str(user_id) if user_id else None)
