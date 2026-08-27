"""Password hashing, JWT issuance/verification, recovery codes."""
from __future__ import annotations

import datetime as dt
import secrets
import uuid

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()

ALG = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, ValueError):
        return False


def create_access_token(user_id: uuid.UUID | str, extra: dict | None = None) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.access_token_minutes),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALG)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[ALG])


def new_refresh_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hex) — only the hash is stored server-side."""
    raw = secrets.token_urlsafe(48)
    return raw, _sha256(raw)


def _sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def generate_recovery_codes(n: int = 8) -> list[str]:
    return [secrets.token_hex(5).upper() for _ in range(n)]


def constant_time_eq(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode(), b.encode())
