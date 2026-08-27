from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class CategoryCreate(BaseModel):
    name: str = Field(max_length=100)
    kind: str = "expense"
    color: str = "#6366f1"
    icon: str = "wallet"


class CategoryOut(CategoryCreate):
    id: uuid.UUID
    user_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class AccountCreate(BaseModel):
    name: str = Field(max_length=200)
    type: str = "depository"
    subtype: str | None = None
    currency: str = Field(min_length=3, max_length=3)
    balance_minor: int = 0


class AccountOut(AccountCreate):
    id: uuid.UUID
    is_manual: bool
    archived: bool
    institution_name: str | None = None

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    account_id: uuid.UUID
    date: date
    amount_minor: int  # signed
    currency: str = Field(min_length=3, max_length=3)
    merchant_raw: str
    description: str | None = None
    category_id: uuid.UUID | None = None
    tags: list[str] = []
    notes_encrypted: str | None = None  # client-side E2E ciphertext
    source: str = "manual"

    @field_validator("merchant_raw")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("merchant_raw must not be empty")
        return v.strip()


class TransactionUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    tags: list[str] | None = None
    notes_encrypted: str | None = None
    needs_review: bool | None = None
    excluded: bool | None = None
    confirmed_by_user: bool | None = None


class SplitIn(BaseModel):
    amount_minor: int
    category_id: uuid.UUID | None = None
    memo: str | None = None


class TransactionOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    user_id: uuid.UUID
    date: date
    amount_minor: int
    currency: str
    merchant_raw: str
    merchant_norm: str
    description: str | None
    category_id: uuid.UUID | None
    tags: list[str] | None
    source: str
    pending: bool
    excluded: bool
    is_income: bool
    categorization_method: str | None
    categorization_confidence: float
    needs_review: bool
    is_split_parent: bool
    created_at: datetime

    model_config = {"from_attributes": True}
