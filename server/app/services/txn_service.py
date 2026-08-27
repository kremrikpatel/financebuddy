"""Transaction domain service — creation pipeline with categorization,
dedup, embedding, split handling and event emission."""
from __future__ import annotations

import hashlib
import uuid
from datetime import date as date_type

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Category, Transaction
from app.services.events import bus, new_event
from app.services.categorizer import categorize, looks_multi_item, normalize_merchant
from app.services.embeddings import embed_texts


def import_hash(account_id: uuid.UUID, date: date_type, amount_minor: int,
                merchant: str, external_id: str | None = None) -> str:
    basis = f"{account_id}|{external_id or ''}|{date.isoformat()}|{amount_minor}|{merchant.strip().lower()}"
    return hashlib.sha256(basis.encode()).hexdigest()


async def find_duplicate(db: AsyncSession, user_id: uuid.UUID, h: str) -> Transaction | None:
    return await db.scalar(
        select(Transaction).where(Transaction.user_id == user_id, Transaction.import_hash == h))


async def create_transaction(
    db: AsyncSession,
    *,
    account: Account,
    date: date_type,
    amount_minor: int,
    currency: str | None = None,
    merchant_raw: str,
    description: str | None = None,
    category_id: uuid.UUID | None = None,
    tags: list[str] | None = None,
    notes_encrypted: str | None = None,
    source: str = "manual",
    external_id: str | None = None,
    pending: bool = False,
    auto_categorize: bool = True,
    skip_events: bool = False,
) -> tuple[Transaction, bool]:
    """Returns (transaction, created). Duplicate-safe via import_hash."""
    currency = (currency or account.currency).upper()
    h = import_hash(account.id, date, amount_minor, merchant_raw, external_id)
    dup = await find_duplicate(db, account.user_id, h)
    if dup:
        return dup, False

    norm = normalize_merchant(merchant_raw)
    is_income = amount_minor > 0
    method, confidence, needs_review = "user", 1.0, False

    if category_id is None and auto_categorize:
        result = await categorize(db, account.user_id, norm, amount_minor, is_income,
                                  text_for_embedding=f"{norm} {description or ''}".strip())
        category_id = result["category_id"]
        method, confidence = result["method"], result["confidence"]
        needs_review = result["needs_review"]
    elif category_id is not None:
        cat = await db.get(Category, category_id)
        method = "user" if source == "manual" else "seed"

    txn = Transaction(
        account_id=account.id, user_id=account.user_id, date=date,
        amount_minor=amount_minor, currency=currency,
        merchant_raw=merchant_raw, merchant_norm=norm, description=description,
        category_id=category_id, tags=tags or [], notes_encrypted=notes_encrypted,
        source=source, external_id=external_id, import_hash=h, pending=pending,
        is_income=is_income, categorization_method=method,
        categorization_confidence=confidence, needs_review=needs_review,
    )
    db.add(txn)
    await db.flush()

    # balance update (assets decrease on spend)
    account.balance_minor += amount_minor

    # async embedding (non-fatal)
    try:
        txn.embedding = (await embed_texts([f"{norm} {description or ''}".strip()]))[0]
    except Exception:
        pass

    # multi-item hint → surface for AI split suggestion
    if looks_multi_item(description, merchant_raw):
        txn.tags = list(set((txn.tags or []) + ["possible-split"]))

    if not skip_events:
        await bus.publish(new_event("transaction.created", str(account.user_id), {
            "transaction_id": str(txn.id), "account_id": str(account.id),
            "amount_minor": amount_minor, "currency": currency,
            "merchant": norm, "date": date.isoformat(),
            "category_id": str(category_id) if category_id else None,
        }))
    return txn, True


async def confirm_category(db: AsyncSession, user_id: uuid.UUID, txn_id: uuid.UUID,
                           category_id: uuid.UUID) -> Transaction | None:
    """User feedback loop — every edit trains the user's kNN model."""
    txn = await db.scalar(select(Transaction).where(
        Transaction.id == txn_id, Transaction.user_id == user_id))
    if not txn:
        return None
    txn.category_id = category_id
    txn.confirmed_by_user = True
    txn.needs_review = False
    txn.categorization_method = "user"
    txn.categorization_confidence = 1.0
    if not txn.embedding:
        txn.embedding = (await embed_texts([txn.merchant_norm]))[0]
    await bus.publish(new_event("transaction.labeled", str(user_id), {
        "transaction_id": str(txn.id), "category_id": str(category_id),
        "merchant_norm": txn.merchant_norm}))
    return txn


async def monthly_flows(db: AsyncSession, user_id: uuid.UUID, months: int = 12,
                        account_ids: list[uuid.UUID] | None = None) -> list[dict]:
    """Aggregate income/expense per month (native account currencies, no conversion)."""
    if _is_sqlite(db):
        month_key = func.strftime("%Y-%m", Transaction.date)
    else:
        month_key = func.to_char(Transaction.date, "YYYY-MM")
    q = (
        select(month_key.label("month"), Transaction.is_income, func.sum(Transaction.amount_minor))
        .where(
            Transaction.user_id == user_id,
            Transaction.excluded.is_(False),
            Transaction.pending.is_(False),
        )
    )
    if account_ids:
        q = q.where(Transaction.account_id.in_(account_ids))
    rows = (await db.execute(q.group_by("month", Transaction.is_income))).all()
    agg: dict[str, dict[str, int]] = {}
    for key, is_income, total in rows:
        bucket = agg.setdefault(key, {"income_minor": 0, "expense_minor": 0})
        if total and total > 0:
            bucket["income_minor"] += total
        else:
            bucket["expense_minor"] += -total
    return [{"month": k, **v} for k, v in sorted(agg.items())][-months:]


def _is_sqlite(db: AsyncSession) -> bool:
    try:
        bind = getattr(db, "bind", None)
        if not bind and hasattr(db, "sync_session"):
            bind = getattr(db.sync_session, "bind", None)
        return bool(bind and getattr(bind, "dialect", None) and bind.dialect.name == "sqlite")
    except Exception:
        return False
