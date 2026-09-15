"""PII masking for every agent/LLM boundary.

Detects and replaces: emails, phone numbers, payment cards (Luhn-validated),
IBANs, SSNs, TFNs, account numbers, long digit sequences.
Masking is one-way per request; a reversible map can be kept in-memory only
and never persisted or logged.
"""
from __future__ import annotations

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_INTL = re.compile(r"\+?\d[\d\s().-]{8,}\d")
CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b", re.I)
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
TFN = re.compile(r"\b\d{3}\s\d{3}\s\d{3}\b")  # Australian Tax File Number style


def _luhn_ok(digits: str) -> bool:
    if not 13 <= len(digits) <= 19:
        return False
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def mask_pii(text: str) -> str:
    out = IBAN.sub("[IBAN]", text)
    out = SSN.sub("[SSN]", out)
    out = EMAIL.sub("[EMAIL]", out)

    def card_repl(m: re.Match) -> str:
        digits = re.sub(r"[^\d]", "", m.group(0))
        return "[CARD]" if _luhn_ok(digits) else m.group(0)

    out = CARD.sub(card_repl, out)

    # phones after cards (cards are longer); before TFN so AU/UK numbers don't hit TFN
    def phone_repl(m: re.Match) -> str:
        digits = re.sub(r"[^\d]", "", m.group(0))
        return "[PHONE]" if len(digits) >= 9 else m.group(0)

    out = PHONE_INTL.sub(phone_repl, out)
    out = re.sub(r"\btfn\b[:\s]*[\d\s]{8,}", "[TFN] ", out, flags=re.I)
    out = TFN.sub("[TFN]", out)

    # residual long account numbers
    out = re.sub(r"\b\d{12,17}\b", "[ACCOUNT]", out)
    return out


class PIIVault:
    """Optional per-request reversible mapping (memory only)."""

    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._counter = 0

    def tokenize(self, text: str) -> tuple[str, dict[str, str]]:
        masked = mask_pii(text)
        self._map.clear()
        return masked, dict(self._map)

    @staticmethod
    def unmask(text: str, mapping: dict[str, str]) -> str:
        result = text
        for token, original in mapping.items():
            result = result.replace(token, original)
        return result
