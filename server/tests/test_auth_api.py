"""API integration tests for authentication, tokens, MFA, vault, and passkeys."""
from __future__ import annotations

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import open_sealed
from app.models import AuditLog, RefreshToken, User


@pytest.mark.asyncio
async def test_register_flow(client: AsyncClient, db_session: AsyncSession):
    payload = {
        "email": "newuser@example.com",
        "password": "SecurePassword123!",
        "full_name": "New User",
        "locale": "en",
        "base_currency": "AUD",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # Verify user in database
    user = await db_session.scalar(select(User).where(User.email == "newuser@example.com"))
    assert user is not None
    assert user.base_currency == "AUD"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user: User):
    payload = {
        "email": test_user.email,
        "password": "SecurePassword123!",
        "full_name": "Duplicate User",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    payload = {
        "email": test_user.email,
        "password": "TestPass123!",
    }
    resp = await client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert not data["mfa_required"]


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, test_user: User):
    payload = {
        "email": test_user.email,
        "password": "WrongPassword999!",
    }
    resp = await client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient, auth_headers: dict[str, str], test_user: User):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == test_user.email
    assert data["base_currency"] == test_user.base_currency


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401 or resp.status_code == 403


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient, test_user: User):
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "TestPass123!",
    })
    tokens = login_resp.json()
    refresh_1 = tokens["refresh_token"]

    # Rotate refresh token
    ref_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert ref_resp.status_code == 200
    new_tokens = ref_resp.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]
    assert new_tokens["refresh_token"] != refresh_1

    # Old refresh token should now be rejected (revoked)
    ref_resp_old = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert ref_resp_old.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_token(client: AsyncClient, test_user: User):
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "TestPass123!",
    })
    tokens = login_resp.json()
    refresh = tokens["refresh_token"]

    logout_resp = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
    assert logout_resp.status_code == 204

    # Now refresh should fail
    ref_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert ref_resp.status_code == 401


@pytest.mark.asyncio
async def test_mfa_setup_confirm_and_login_flow(
    client: AsyncClient, auth_headers: dict[str, str], test_user: User, db_session: AsyncSession
):
    # 1. Start MFA setup
    setup_resp = await client.post("/api/v1/auth/mfa/setup", headers=auth_headers)
    assert setup_resp.status_code == 200
    mfa_data = setup_resp.json()
    assert "secret" in mfa_data
    assert "otpauth_uri" in mfa_data
    secret = mfa_data["secret"]

    # 2. Generate valid TOTP code
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()

    # 3. Confirm MFA
    confirm_resp = await client.post("/api/v1/auth/mfa/confirm", headers=auth_headers, json={"code": valid_code})
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()
    assert confirm_data["enabled"] is True
    assert len(confirm_data["recovery_codes"]) == 8

    # 4. Login without TOTP should indicate mfa_required
    login_attempt_1 = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "TestPass123!",
    })
    assert login_attempt_1.status_code == 200
    l1_data = login_attempt_1.json()
    assert l1_data["mfa_required"] is True
    assert l1_data["access_token"] == ""

    # 5. Login with TOTP code
    code_now = totp.now()
    login_attempt_2 = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "TestPass123!",
        "totp_code": code_now,
    })
    assert login_attempt_2.status_code == 200
    l2_data = login_attempt_2.json()
    assert l2_data["access_token"]
    assert l2_data["refresh_token"]

    # 6. Disable MFA
    disable_code = totp.now()
    dis_resp = await client.post("/api/v1/auth/mfa/disable", headers=auth_headers, json={"code": disable_code})
    assert dis_resp.status_code == 200
    assert dis_resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_zero_knowledge_vault_endpoints(client: AsyncClient, auth_headers: dict[str, str]):
    vault_payload = {
        "kdf": "argon2id",
        "kdf_salt_hex": "0123456789abcdef0123456789abcdef",
        "wrapped_dek_b64": "wrapped-data-key-ciphertext",
        "verifier_b64": "verifier-hash-base64",
        "algo": "aes-256-gcm",
    }
    setup_resp = await client.post("/api/v1/auth/vault", headers=auth_headers, json=vault_payload)
    assert setup_resp.status_code == 200
    assert setup_resp.json()["status"] == "vault_ready"

    get_resp = await client.get("/api/v1/auth/vault", headers=auth_headers)
    assert get_resp.status_code == 200
    vault_get = get_resp.json()
    assert vault_get["kdf"] == "argon2id"
    assert vault_get["kdf_salt_hex"] == vault_payload["kdf_salt_hex"]
    assert vault_get["wrapped_dek_b64"] == vault_payload["wrapped_dek_b64"]
    assert vault_get["verifier_b64"] == vault_payload["verifier_b64"]


@pytest.mark.asyncio
async def test_passkey_options_generation(client: AsyncClient, auth_headers: dict[str, str]):
    # Passkey registration start
    reg_start_resp = await client.post("/api/v1/auth/passkeys/register/start", headers=auth_headers)
    assert reg_start_resp.status_code == 200
    reg_data = reg_start_resp.json()
    assert "options" in reg_data
    assert "challenge_token" in reg_data
    assert "challenge" in reg_data["options"]

    # Passkey auth start
    auth_start_resp = await client.post("/api/v1/auth/passkeys/auth/start", json={})
    assert auth_start_resp.status_code == 200
    auth_data = auth_start_resp.json()
    assert "options" in auth_data
    assert "challenge_token" in auth_data
