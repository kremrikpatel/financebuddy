import uuid

from pydantic import BaseModel, Field


class ChatSendIn(BaseModel):
    thread_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=8000)
    agent_mode: str = "auto"  # auto|coach|fraud|budget|goals|assistant


class ThreadOut(BaseModel):
    id: uuid.UUID
    title: str
    agent_mode: str

    model_config = {"from_attributes": True}


class QuickAddParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    account_id: uuid.UUID | None = None
    currency: str = "USD"


class ParsedExpense(BaseModel):
    amount_minor: int
    currency: str
    merchant: str
    date: str | None = None
    category_guess: str | None = None
    items: list[dict] | None = None
    confidence: float = 0.5
