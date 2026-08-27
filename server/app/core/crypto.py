"""Server-side envelope encryption (AES-256-GCM) for secrets at rest
(bank tokens, MFA secrets, passkey state). Zero-knowledge user vault keys
are handled client-side and never decrypted here.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


class CryptoBox:
    def __init__(self, key_hex: str) -> None:
        self._key = bytes.fromhex(key_hex)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ct = AESGCM(self._key).encrypt(nonce, plaintext.encode(), None)
        return base64.urlsafe_b64encode(nonce + ct).decode()

    def decrypt(self, token: str) -> str:
        raw = base64.urlsafe_b64decode(token.encode())
        nonce, ct = raw[:12], raw[12:]
        return AESGCM(self._key).decrypt(nonce, ct, None).decode()


_box = CryptoBox(settings.data_encryption_key)


def seal(plaintext: str) -> str:
    return _box.encrypt(plaintext)


def open_sealed(token: str) -> str:
    return _box.decrypt(token)
