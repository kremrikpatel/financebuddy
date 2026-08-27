from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models import PasskeyCredential, User
from app.schemas.auth import (
    LoginIn,
    MFAEnableOut,
    MFAVerifyIn,
    PasskeyAuthStartIn,
    RefreshIn,
    RegisterIn,
    TokenPair,
    UserOut,
    VaultSetupIn,
)
from app.services import auth_service
from app.services.deps import client_agent, client_ip, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _challenge_token(challenge: bytes) -> str:
    """Stateless signed round-trip for WebAuthn challenges."""
    import jwt

    return pyjwt.encode({"ch": base64.urlsafe_b64encode(challenge).decode()},
                        settings.secret_key, algorithm="HS256")


def _challenge_from_token(token: str) -> bytes:
    try:
        payload = decode_token(token)
        return base64.urlsafe_b64decode(payload["ch"])
    except Exception:
        raise HTTPException(400, "Invalid or expired challenge")


@router.post("/register", response_model=TokenPair, status_code=201)
async def register(body: RegisterIn, request: Request,
                   db: AsyncSession = Depends(get_db)):
    user = await auth_service.register(db, body.email, body.password, body.full_name,
                                       body.locale, body.base_currency)
    access, refresh = await auth_service.issue_tokens(db, user, client_agent(request))
    await auth_service.audit(db, "auth.register", user.id, client_ip(request))
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    user, mfa_ok = await auth_service.authenticate(
        db, body.email, body.password, body.totp_code, body.recovery_code)
    if not mfa_ok:
        await auth_service.audit(db, "auth.mfa_challenge", user.id, client_ip(request))
        return TokenPair(access_token="", refresh_token=None, mfa_required=True)
    access, refresh = await auth_service.issue_tokens(db, user, client_agent(request))
    await auth_service.audit(db, "auth.login", user.id, client_ip(request))
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshIn, request: Request, db: AsyncSession = Depends(get_db)):
    _user, access, new_refresh = await auth_service.rotate_refresh(
        db, body.refresh_token, client_agent(request))
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
async def logout(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    from app.core.security import _sha256

    from app.models import RefreshToken

    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _sha256(body.refresh_token)))
    if row:
        row.revoked_at = datetime.now(UTC)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


# ── MFA ─────────────────────────────────────────────────────────────────

@router.post("/mfa/setup", response_model=MFAEnableOut)
async def mfa_setup(user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    secret, uri = await auth_service.enable_mfa_start(db, user)
    return MFAEnableOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/confirm")
async def mfa_confirm(body: MFAVerifyIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db), request: Request = None):
    codes = await auth_service.enable_mfa_confirm(db, user, body.code)
    await auth_service.audit(db, "auth.mfa_enabled", user.id,
                             client_ip(request) if request else None)
    return {"enabled": True, "recovery_codes": codes}


@router.post("/mfa/disable")
async def mfa_disable(body: MFAVerifyIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    await auth_service.disable_mfa(db, user, body.code)
    return {"enabled": False}


# ── Zero-knowledge vault ────────────────────────────────────────────────

@router.post("/vault")
async def vault_setup(body: VaultSetupIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    await auth_service.vault_setup(db, user, body.model_dump())
    return {"status": "vault_ready"}


@router.get("/vault")
async def vault_get(user: User = Depends(get_current_user)):
    return {
        "kdf": user.vault_algo,
        "kdf_salt_hex": user.vault_salt,
        "wrapped_dek_b64": user.vault_wrapped_dek,
        "verifier_b64": user.vault_verifier,
        "algo": user.vault_algo,
    }


# ── Passkeys / biometrics ───────────────────────────────────────────────

@router.post("/passkeys/register/start")
async def passkey_start(request: Request, user: User = Depends(get_current_user)):
    origin = request.headers.get("origin") or str(request.base_url).rstrip("/")
    options = auth_service.passkey_register_options(user, origin)
    return {"options": options, "challenge_token": _challenge_token(_extract_challenge(options))}


def _extract_challenge(options: dict) -> bytes:
    ch = options["challenge"]
    padding = "=" * (-len(ch) % 4)
    return base64.urlsafe_b64decode(ch + padding)


@router.post("/passkeys/register/finish")
async def passkey_finish(request: Request, body: dict,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if "challenge_token" not in body:
        raise HTTPException(400, "Missing challenge_token")
    challenge = _challenge_from_token(body.pop("challenge_token"))
    origin = request.headers.get("origin") or str(request.base_url).rstrip("/")
    label = body.get("label")
    cred_data = body.get("credential") or body
    cred = await auth_service.passkey_register_finish(
        db, user, cred_data, challenge, label, origin)
    await auth_service.audit(db, "auth.passkey_registered", user.id, client_ip(request))
    return {"credential_id": cred.credential_id}


@router.post("/passkeys/auth/start")
async def passkey_auth_start(request: Request, body: PasskeyAuthStartIn | None = None,
                             db: AsyncSession = Depends(get_db)):
    creds: list[PasskeyCredential] = []
    if body and body.email:
        user = await db.scalar(select(User).where(User.email == body.email.lower()))
        if not user:
            raise HTTPException(404, "No account for email")
        creds = list((await db.execute(select(PasskeyCredential).where(
            PasskeyCredential.user_id == user.id))).scalars().all())
    origin = request.headers.get("origin") or str(request.base_url).rstrip("/")
    options = auth_service.passkey_auth_options(creds, origin)
    return {"options": options, "challenge_token": _challenge_token(_extract_challenge(options))}


@router.post("/passkeys/auth/finish", response_model=TokenPair)
async def passkey_auth_finish(request: Request, body: dict,
                              db: AsyncSession = Depends(get_db)):
    if "challenge_token" not in body:
        raise HTTPException(400, "Missing challenge_token")
    challenge = _challenge_from_token(body.pop("challenge_token"))
    cred_data = body.get("credential") or body
    raw_id = cred_data.get("id") or cred_data.get("rawId") or ""
    pad = "=" * (-len(raw_id) % 4)
    try:
        normalized = base64.urlsafe_b64encode(base64.urlsafe_b64decode(raw_id + pad)).decode()
    except Exception:
        normalized = raw_id
    origin = request.headers.get("origin") or str(request.base_url).rstrip("/")
    cred = await auth_service.passkey_auth_finish(
        db, cred_data, challenge, normalized, origin)
    user = await db.get(User, cred.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "User inactive or not found")
    access, refresh = await auth_service.issue_tokens(db, user, client_agent(request))
    await auth_service.audit(db, "auth.login_passkey", user.id, client_ip(request))
    return TokenPair(access_token=access, refresh_token=refresh)


# ── Sessions & audit ────────────────────────────────────────────────────

@router.get("/sessions")
async def sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(PasskeyCredential).where(PasskeyCredential.user_id == user.id))).scalars().all()
    return {"passkeys": [{"id": r.id.__str__(), "label": r.label, "created_at": str(r.created_at)} for r in rows]}


@router.delete("/sessions/all", status_code=204)
async def revoke_sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await auth_service.revoke_all_sessions(db, user.id)
    return Response(status_code=204)
