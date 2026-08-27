"""Tests for security, encryption, and cryptographic primitives."""
import pytest

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


def test_argon2id_hashing():
    pw = "VeryStrongPassword123!@#"
    hashed = hash_password(pw)
    assert hashed.startswith("$argon2id$")
    assert verify_password(pw, hashed)
    assert not verify_password("WrongPassword123!", hashed)


def test_envelope_encryption_roundtrip():
    secret = "secret-bank-access-token-xyz-12345"
    sealed = seal(secret)
    assert sealed != secret
    unsealed = open_sealed(sealed)
    assert unsealed == secret


def test_envelope_encryption_random_nonce():
    secret = "same-plaintext-secret"
    s1 = seal(secret)
    s2 = seal(secret)
    # Ciphertexts must differ due to random 12-byte nonce
    assert s1 != s2
    assert open_sealed(s1) == secret
    assert open_sealed(s2) == secret


def test_custom_cryptobox():
    key_hex = "11" * 32
    box = CryptoBox(key_hex)
    plain = "sensitive-data-payload"
    enc = box.encrypt(plain)
    dec = box.decrypt(enc)
    assert dec == plain


def test_jwt_claims_and_expiry():
    import uuid
    uid = uuid.uuid4()
    token = create_access_token(uid, {"role": "admin"})
    decoded = decode_token(token)
    assert decoded["sub"] == str(uid)
    assert decoded["type"] == "access"
    assert decoded["role"] == "admin"
    assert "exp" in decoded
    assert "jti" in decoded


def test_recovery_codes():
    codes = generate_recovery_codes(8)
    assert len(codes) == 8
    assert len(set(codes)) == 8
    for code in codes:
        assert len(code) == 10  # 5 bytes hex


def test_constant_time_eq():
    assert constant_time_eq("secret123", "secret123")
    assert not constant_time_eq("secret123", "secret456")
    assert not constant_time_eq("short", "longer_secret")


def test_refresh_token_generation():
    raw, token_hash = new_refresh_token()
    assert len(raw) > 40
    assert len(token_hash) == 64  # SHA-256 hex string
