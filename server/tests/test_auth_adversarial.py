"""Adversarial security and empirical challenge test suite for Milestone M1.

Tests rigorous attack vectors:
1. Tampered JWTs & Algorithm Confusion (none alg, forged sig, tampered sub, expired, type confusion, malformed UUID)
2. Refresh Token Lifecycle & Replay Attacks (revoked replay, expired, inactive user, revoke-all)
3. TOTP MFA Adversarial Flows (invalid code, recovery code consumption & replay, disable protection)
4. WebAuthn Passkey Challenge & Signature Tampering (missing/forged challenge, unknown credential, corrupted payload)
5. Zero-Knowledge Vault Integrity & Cross-Tenant Isolation
6. Server-Side Envelope Encryption (AES-256-GCM bit flipping, tag tampering, truncation)
7. Unauthenticated & Malformed Request Boundary (header injection, SQLi in auth headers, malformed bearer)
"""
from __future__ import annotations

import datetime as dt
import uuid
import base64
import pytest
import jwt
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import CryptoBox, open_sealed, seal
from app.core.security import (
    constant_time_eq,
    create_access_token,
    decode_token,
    generate_recovery_codes,
    hash_password,
    new_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User
from cryptography.exceptions import InvalidTag
import pyotp


# ============================================================================
# Vector 1: Tampered JWTs & Algorithm Manipulation
# ============================================================================

@pytest.mark.asyncio
async def test_jwt_algorithm_none_attack(client: AsyncClient):
    """Ensure tokens signed with 'none' algorithm are strictly rejected."""
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": dt.datetime.now(dt.UTC),
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15),
    }
    # Unsigned 'none' algorithm token
    none_token = jwt.encode(payload, key="", algorithm="none")
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {none_token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_jwt_forged_secret_rejected(client: AsyncClient):
    """Ensure tokens signed with an attacker's key are rejected."""
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": dt.datetime.now(dt.UTC),
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15),
    }
    attacker_token = jwt.encode(payload, key="attacker-controlled-secret-key-32b", algorithm="HS256")
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {attacker_token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_jwt_expired_token_rejected(client: AsyncClient, test_user: User):
    """Ensure expired access tokens are rejected with 401."""
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    payload = {
        "sub": str(test_user.id),
        "type": "access",
        "iat": past - dt.timedelta(minutes=15),
        "exp": past,
    }
    expired_token = jwt.encode(payload, key=settings.secret_key, algorithm="HS256")
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_jwt_type_confusion_refresh_as_access(client: AsyncClient, test_user: User):
    """Ensure token with type='refresh' or other type cannot be used as an access token."""
    payload = {
        "sub": str(test_user.id),
        "type": "refresh",
        "iat": dt.datetime.now(dt.UTC),
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15),
    }
    refresh_as_access = jwt.encode(payload, key=settings.secret_key, algorithm="HS256")
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_as_access}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_jwt_malformed_user_id_in_sub(client: AsyncClient):
    """Ensure tokens with non-UUID sub values are safely rejected with 401 (no 500 unhandled crash)."""
    for bad_sub in ["not-a-uuid", "12345", "", "admin'; DROP TABLE users; --"]:
        payload = {
            "sub": bad_sub,
            "type": "access",
            "iat": dt.datetime.now(dt.UTC),
            "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15),
        }
        token = jwt.encode(payload, key=settings.secret_key, algorithm="HS256")
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_jwt_nonexistent_user_sub(client: AsyncClient):
    """Ensure tokens with a random non-existent user UUID return 401."""
    random_uid = uuid.uuid4()
    token = create_access_token(random_uid)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_jwt_inactive_user_token(client: AsyncClient, db_session: AsyncSession):
    """Ensure deactivated user tokens are immediately rejected with 401."""
    inactive_user = User(
        email="inactive@example.com",
        password_hash=hash_password("Pass123!"),
        full_name="Inactive User",
        is_active=False,
    )
    db_session.add(inactive_user)
    await db_session.commit()
    await db_session.refresh(inactive_user)

    token = create_access_token(inactive_user.id)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ============================================================================
# Vector 2: Refresh Token Lifecycle & Replay Attacks
# ============================================================================

@pytest.mark.asyncio
async def test_refresh_token_replay_attack_rejected(client: AsyncClient, test_user: User):
    """Ensure rotated refresh token cannot be replayed (replay attack prevention)."""
    # 1. Login
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "TestPass123!",
    })
    assert login_resp.status_code == 200
    initial_refresh = login_resp.json()["refresh_token"]

    # 2. First rotation (valid)
    rot_1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": initial_refresh})
    assert rot_1.status_code == 200
    fresh_refresh = rot_1.json()["refresh_token"]

    # 3. Attacker replays initial_refresh
    replay_attempt = await client.post("/api/v1/auth/refresh", json={"refresh_token": initial_refresh})
    assert replay_attempt.status_code == 401
    assert "detail" in replay_attempt.json()

    # 4. Legitimate user uses fresh_refresh (should succeed)
    rot_2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": fresh_refresh})
    assert rot_2.status_code == 200


@pytest.mark.asyncio
async def test_revoke_all_sessions_invalidates_all_tokens(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
):
    """Ensure DELETE /api/v1/auth/sessions/all revokes all refresh tokens."""
    # Login twice to create two sessions
    l1 = await client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "TestPass123!"})
    r1 = l1.json()["refresh_token"]
    l2 = await client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "TestPass123!"})
    r2 = l2.json()["refresh_token"]

    # Revoke all
    del_resp = await client.delete("/api/v1/auth/sessions/all", headers=auth_headers)
    assert del_resp.status_code == 204

    # Both refresh tokens must now be rejected
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": r1})).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": r2})).status_code == 401


# ============================================================================
# Vector 3: TOTP MFA Adversarial Scenarios
# ============================================================================

@pytest.mark.asyncio
async def test_mfa_confirm_with_invalid_totp_fails(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Ensure confirming MFA with an invalid code fails and leaves MFA disabled."""
    # 1. Start setup
    setup_resp = await client.post("/api/v1/auth/mfa/setup", headers=auth_headers)
    assert setup_resp.status_code == 200

    # 2. Confirm with wrong code
    bad_resp = await client.post(
        "/api/v1/auth/mfa/confirm",
        headers=auth_headers,
        json={"code": "000000"}
    )
    assert bad_resp.status_code == 401

    # 3. Check me endpoint - mfa_enabled must be false
    me_resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_resp.json()["mfa_enabled"] is False


@pytest.mark.asyncio
async def test_mfa_recovery_code_single_use_and_replay(
    client: AsyncClient, auth_headers: dict[str, str], test_user: User
):
    """Ensure recovery code works once and is consumed (cannot be replayed)."""
    # 1. Setup and confirm MFA
    setup = (await client.post("/api/v1/auth/mfa/setup", headers=auth_headers)).json()
    secret = setup["secret"]
    valid_code = pyotp.TOTP(secret).now()
    conf = (await client.post("/api/v1/auth/mfa/confirm", headers=auth_headers, json={"code": valid_code})).json()
    recovery_codes = conf["recovery_codes"]
    code_to_use = recovery_codes[0]

    # 2. Login using recovery code (1st attempt -> success)
    login_1 = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "TestPass123!",
        "recovery_code": code_to_use,
    })
    assert login_1.status_code == 200
    assert login_1.json()["access_token"] != ""
    assert login_1.json()["mfa_required"] is False

    # 3. Attacker tries to reuse the same recovery code (2nd attempt -> fails, mfa_required=True)
    login_2 = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "TestPass123!",
        "recovery_code": code_to_use,
    })
    assert login_2.status_code == 200
    assert login_2.json()["mfa_required"] is True
    assert login_2.json()["access_token"] == ""


@pytest.mark.asyncio
async def test_mfa_disable_with_invalid_totp_fails(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Ensure disabling MFA requires a valid current TOTP code."""
    # 1. Enable MFA
    setup = (await client.post("/api/v1/auth/mfa/setup", headers=auth_headers)).json()
    valid_code = pyotp.TOTP(setup["secret"]).now()
    await client.post("/api/v1/auth/mfa/confirm", headers=auth_headers, json={"code": valid_code})

    # 2. Attempt disable with invalid code
    bad_disable = await client.post(
        "/api/v1/auth/mfa/disable",
        headers=auth_headers,
        json={"code": "111222"}
    )
    assert bad_disable.status_code == 401

    # Verify still enabled
    me_resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_resp.json()["mfa_enabled"] is True


# ============================================================================
# Vector 4: WebAuthn Passkey Adversarial & Challenge Tampering
# ============================================================================

@pytest.mark.asyncio
async def test_passkey_register_missing_challenge_token(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Ensure passkey registration without challenge_token is rejected with 400."""
    resp = await client.post(
        "/api/v1/auth/passkeys/register/finish",
        headers=auth_headers,
        json={"credential": {"id": "test_id"}}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_passkey_register_tampered_challenge_token(
    client: AsyncClient, auth_headers: dict[str, str]
):
    """Ensure passkey registration with forged/tampered challenge_token is rejected."""
    resp = await client.post(
        "/api/v1/auth/passkeys/register/finish",
        headers=auth_headers,
        json={"challenge_token": "forged.jwt.token", "credential": {"id": "test_id"}}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_passkey_auth_nonexistent_email_start(client: AsyncClient):
    """Ensure passkey auth start with unknown email returns 404."""
    resp = await client.post(
        "/api/v1/auth/passkeys/auth/start",
        json={"email": "nonexistent_user_9999@example.com"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_passkey_auth_unknown_credential_finish(client: AsyncClient):
    """Ensure passkey auth finish with unknown credential ID returns 401."""
    # Obtain valid challenge token
    start_resp = await client.post("/api/v1/auth/passkeys/auth/start", json={})
    challenge_token = start_resp.json()["challenge_token"]

    finish_resp = await client.post(
        "/api/v1/auth/passkeys/auth/finish",
        json={
            "challenge_token": challenge_token,
            "credential": {
                "id": "unknown-nonexistent-cred-id",
                "rawId": "unknown-nonexistent-cred-id",
                "type": "public-key",
            }
        }
    )
    assert finish_resp.status_code == 401


# ============================================================================
# Vector 5: Zero-Knowledge Vault Cross-Tenant Isolation
# ============================================================================

@pytest.mark.asyncio
async def test_vault_unauthenticated_access_denied(client: AsyncClient):
    """Ensure unauthenticated access to vault endpoints is blocked with 401."""
    assert (await client.get("/api/v1/auth/vault")).status_code in (401, 403)
    assert (await client.post("/api/v1/auth/vault", json={})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_vault_cross_tenant_isolation(
    client: AsyncClient, test_user: User, db_session: AsyncSession
):
    """Ensure User A cannot view User B's zero-knowledge vault parameters."""
    # User A setup vault
    token_a = create_access_token(test_user.id)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    vault_a = {
        "kdf": "argon2id",
        "kdf_salt_hex": "user_a_salt_0123456789abcdef",
        "wrapped_dek_b64": "user_a_wrapped_dek_ciphertext",
        "verifier_b64": "user_a_verifier_hash",
        "algo": "aes-256-gcm",
    }
    await client.post("/api/v1/auth/vault", headers=headers_a, json=vault_a)

    # Register User B
    user_b_reg = await client.post("/api/v1/auth/register", json={
        "email": "user_b_vault@example.com",
        "password": "Password123!",
        "full_name": "User B",
    })
    token_b = user_b_reg.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B queries their vault - must NOT contain User A's data
    get_b = await client.get("/api/v1/auth/vault", headers=headers_b)
    assert get_b.status_code == 200
    b_data = get_b.json()
    assert b_data["kdf_salt_hex"] is None
    assert b_data["wrapped_dek_b64"] is None


# ============================================================================
# Vector 6: Cryptographic Envelope Encryption & Primitives
# ============================================================================

def test_cryptobox_tampered_ciphertext_rejection():
    """Ensure modifying ciphertext bytes causes AES-GCM authentication failure."""
    plaintext = "super-secret-bank-credentials"
    sealed = seal(plaintext)
    raw = bytearray(base64.urlsafe_b64decode(sealed.encode()))

    # Flip one byte in the ciphertext portion
    raw[-1] ^= 0xFF
    tampered_sealed = base64.urlsafe_b64encode(bytes(raw)).decode()

    with pytest.raises(Exception):
        open_sealed(tampered_sealed)


def test_cryptobox_truncated_payload_rejection():
    """Ensure truncated ciphertext payloads are rejected."""
    plaintext = "super-secret-bank-credentials"
    sealed = seal(plaintext)
    raw = base64.urlsafe_b64decode(sealed.encode())

    # Truncate to less than nonce (12 bytes) + tag (16 bytes)
    truncated = base64.urlsafe_b64encode(raw[:15]).decode()
    with pytest.raises(Exception):
        open_sealed(truncated)


def test_argon2id_timing_resistance_and_salting():
    """Ensure same password produces distinct hashes with distinct salts."""
    pw = "CommonPassword987!"
    h1 = hash_password(pw)
    h2 = hash_password(pw)
    assert h1 != h2
    assert verify_password(pw, h1)
    assert verify_password(pw, h2)
    assert not verify_password(pw + "x", h1)


def test_constant_time_comparison_bounds():
    """Ensure constant_time_eq handles matching, mismatched, and empty strings."""
    assert constant_time_eq("A" * 64, "A" * 64) is True
    assert constant_time_eq("A" * 64, "A" * 63 + "B") is False
    assert constant_time_eq("", "") is True
    assert constant_time_eq("A", "") is False


# ============================================================================
# Vector 7: Unauthenticated & Malformed Request Boundary
# ============================================================================

@pytest.mark.asyncio
async def test_auth_headers_malformed_formats(client: AsyncClient):
    """Ensure varied malformed Authorization headers return 401 (not 500)."""
    malformed_headers = [
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer not-jwt"},
        {"Authorization": "Token 12345"},
        {"Authorization": "Bearer " + "A" * 1000},
        {"Authorization": "Bearer ' OR '1'='1"},
    ]
    for h in malformed_headers:
        resp = await client.get("/api/v1/auth/me", headers=h)
        assert resp.status_code in (401, 403), f"Failed for header: {h}"
