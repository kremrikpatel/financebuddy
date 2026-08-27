from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class BudgetEnvelopeIO(BaseModel):
    category_id: uuid.UUID | None = None
    name: str | None = None
    allocated_minor: int = 0
    rollover: bool = False


class BudgetCreate(BaseModel):
    name: str = Field(max_length=120)
    strategy: str = Field(pattern="^(envelope|zero_based|traditional)$")
    start_date: date
    income_planned_minor: int = 0
    currency: str = "USD"
    envelopes: list[BudgetEnvelopeIO] = []


class BudgetOut(BaseModel):
    id: uuid.UUID
    name: str
    strategy: str
    period: str
    start_date: date
    income_planned_minor: int
    currency: str
    active: bool

    model_config = {"from_attributes": True}


class GoalCreate(BaseModel):
    name: str = Field(max_length=200)
    target_minor: int = Field(gt=0)
    currency: str = "USD"
    target_date: date | None = None
    strategy: str = Field(default="fixed_monthly", pattern="^(fixed_monthly|percent_income|round_up)$")
    monthly_amount_minor: int = 0
    percent_of_income: float = Field(default=0.0, ge=0, le=100)
    account_id: uuid.UUID | None = None


class GoalContributionIn(BaseModel):
    amount_minor: int = Field(gt=0)


class GoalOut(BaseModel):
    id: uuid.UUID
    name: str
    target_minor: int
    saved_minor: int
    currency: str
    target_date: date | None
    strategy: str
    on_track: bool = True

    model_config = {"from_attributes": True}


class DebtCreate(BaseModel):
    name: str = Field(max_length=200)
    principal_minor: int = Field(gt=0)
    apr_bps: int = Field(ge=0, le=10000)
    min_payment_minor: int = Field(gt=0)
    due_day: int | None = Field(default=None, ge=1, le=31)
    currency: str = "USD"


class DebtPayoffPlan(BaseModel):
    strategy: str
    months: int
    total_interest_minor: int
    payoff_order: list[dict]
    schedule: list[dict]


class AlertOut(BaseModel):
    id: uuid.UUID
    type: str
    severity: str
    title: str
    body: str | None
    payload: dict | None
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
