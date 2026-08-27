from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str | None = None
    locale: str = "en"
    base_currency: str = "USD"


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None
    recovery_code: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    mfa_required: bool = False


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    locale: str
    base_currency: str
    mfa_enabled: bool

    model_config = {"from_attributes": True}


class MFAEnableOut(BaseModel):
    secret: str
    otpauth_uri: str


class MFAVerifyIn(BaseModel):
    code: str


class VaultSetupIn(BaseModel):
    """Client-side derived material — server stores opaque blobs only."""

    kdf: str = Field(pattern="^(argon2id|pbkdf2)$")
    kdf_salt_hex: str = Field(min_length=16)
    wrapped_dek_b64: str
    verifier_b64: str
    algo: str = "aes-256-gcm"


class VaultUnlockIn(BaseModel):
    verifier_b64: str


class PasskeyRegisterStartOut(BaseModel):
    options: dict


class PasskeyRegisterFinishIn(BaseModel):
    credential: dict
    label: str | None = None


class PasskeyAuthStartIn(BaseModel):
    email: EmailStr | None = None


class PasskeyAuthFinishIn(BaseModel):
    credential: dict
