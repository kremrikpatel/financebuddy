from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Account, Category, Transaction
from app.schemas.finance import (
    AccountCreate,
    AccountOut,
    CategoryCreate,
    CategoryOut,
    SplitIn,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.services.deps import get_current_user
from app.models import User
from app.services import txn_service
from app.services.categorizer import categorize as auto_categorize_txn
from app.services.importers import ImportReport, ingest, parse_csv, parse_ofx
from app.services.receipt_ocr import ocr_receipt

router = APIRouter(tags=["finance"])


# ── Accounts ────────────────────────────────────────────────────────────

@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Account).where(Account.user_id == user.id)
        .order_by(Account.created_at))).scalars().all()
    return rows


@router.post("/accounts", response_model=AccountOut, status_code=201)
async def create_account(body: AccountCreate, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    acct = Account(user_id=user.id, name=body.name, type=body.type,
                   subtype=body.subtype, currency=body.currency.upper(),
                   balance_minor=body.balance_minor, is_manual=True)
    db.add(acct)
    await db.flush()
    return acct


@router.delete("/accounts/{account_id}", status_code=204)
async def archive_account(account_id: uuid.UUID, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    acct = await _own_account(db, user, account_id)
    acct.archived = True
    return None


async def _own_account(db: AsyncSession, user: User, account_id: uuid.UUID) -> Account:
    acct = await db.get(Account, account_id)
    if not acct or acct.user_id != user.id:
        raise HTTPException(404, "Account not found")
    return acct


# ── Transactions ────────────────────────────────────────────────────────

@router.get("/transactions", response_model=list[TransactionOut])
async def list_transactions(
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    needs_review: bool | None = None,
    start: date | None = None,
    end: date | None = None,
    search: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Transaction).where(Transaction.user_id == user.id)
    if account_id:
        q = q.where(Transaction.account_id == account_id)
    if category_id:
        q = q.where(Transaction.category_id == category_id)
    if needs_review is not None:
        q = q.where(Transaction.needs_review == needs_review)
    if start:
        q = q.where(Transaction.date >= start)
    if end:
        q = q.where(Transaction.date <= end)
    if search:
        q = q.where(Transaction.merchant_norm.ilike(f"%{search.lower()}%"))
    q = q.order_by(Transaction.date.desc(), Transaction.created_at.desc()).offset(offset).limit(limit)
    return (await db.execute(q)).scalars().all()


@router.post("/transactions", response_model=TransactionOut, status_code=201)
async def create_transaction(body: TransactionCreate, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    account = await _own_account(db, user, body.account_id)
    txn, _created = await txn_service.create_transaction(
        db, account=account, date=body.date, amount_minor=body.amount_minor,
        currency=body.currency, merchant_raw=body.merchant_raw,
        description=body.description, category_id=body.category_id,
        tags=body.tags, notes_encrypted=body.notes_encrypted, source="manual")
    return txn


@router.patch("/transactions/{txn_id}", response_model=TransactionOut)
async def update_transaction(txn_id: uuid.UUID, body: TransactionUpdate,
                             user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    """User edits here feed the categorization feedback loop."""
    txn = await db.scalar(select(Transaction).where(
        Transaction.id == txn_id, Transaction.user_id == user.id))
    if not txn:
        raise HTTPException(404, "Transaction not found")
    data = body.model_dump(exclude_unset=True)
    new_cat = data.pop("category_id", None)
    if body.confirmed_by_user and new_cat is not None and new_cat != str(txn.category_id):
        txn = await txn_service.confirm_category(db, user.id, txn_id, new_cat) or txn
    else:
        if new_cat is not None:
            txn.category_id = new_cat
            txn.confirmed_by_user = True
            txn.needs_review = False
            txn.categorization_method = "user"
        for key, value in data.items():
            setattr(txn, key, value)
    await db.flush()
    await db.refresh(txn)
    return txn


@router.post("/transactions/{txn_id}/splits", status_code=201)
async def add_split(txn_id: uuid.UUID, body: SplitIn,
                    user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    from app.models import TransactionSplit

    txn = await db.scalar(select(Transaction).where(
        Transaction.id == txn_id, Transaction.user_id == user.id))
    if not txn:
        raise HTTPException(404, "Transaction not found")
    total_splits = (await db.execute(
        select(func.coalesce(func.sum(TransactionSplit.amount_minor), 0))
        .where(TransactionSplit.transaction_id == txn_id))).scalar_one()
    if abs(total_splits + body.amount_minor) > abs(txn.amount_minor):
        raise HTTPException(400, "Splits exceed transaction amount")
    split = TransactionSplit(transaction_id=txn_id, amount_minor=body.amount_minor,
                             category_id=body.category_id, memo=body.memo)
    txn.is_split_parent = True
    db.add(split)
    await db.flush()
    return {"id": split.id, "remaining_minor": abs(txn.amount_minor) - abs(total_splits + body.amount_minor)}


@router.post("/transactions/suggest-split")
async def suggest_split(txn_id: uuid.UUID, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """AI multi-item split suggestion for a transaction."""
    txn = await db.scalar(select(Transaction).where(
        Transaction.id == txn_id, Transaction.user_id == user.id))
    if not txn:
        raise HTTPException(404, "Transaction not found")
    try:
        from app.ai.llm_router import complete_json

        prompt = (
            f"Bank transaction may contain multiple purchases bundled together.\n"
            f"Merchant: {txn.merchant_raw}\nDescription: {txn.description or 'n/a'}\n"
            f"Total: {abs(txn.amount_minor)/100:.2f} {txn.currency}\n"
            'If it plausibly contains multiple items, reply JSON:\n'
            '{"multi_item": true, "items": [{"label": "...", "amount_minor": 123}]}, '
            'sum of items must equal the total. Otherwise {"multi_item": false}.'
        )
        result = await complete_json(prompt)
        return {"transaction_id": str(txn_id), **(result or {"multi_item": False})}
    except Exception:
        return {"transaction_id": str(txn_id), "multi_item": False,
                "error": "LLM unavailable — split manually."}


# ── Categories ──────────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Category).where((Category.user_id == user.id) | (Category.user_id.is_(None)))
        .order_by(Category.name))).scalars().all()
    return rows


@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(body: CategoryCreate, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    cat = Category(user_id=user.id, name=body.name, kind=body.kind,
                   color=body.color, icon=body.icon)
    db.add(cat)
    await db.flush()
    return cat


# ── Imports (CSV / OFX / receipts) ──────────────────────────────────────

async def _handle_csv_import(account_id: uuid.UUID, file: UploadFile, user: User, db: AsyncSession):
    account = await _own_account(db, user, account_id)
    content = await file.read()
    try:
        txns = parse_csv(content)
    except Exception as exc:
        raise HTTPException(400, f"CSV parse failed: {exc}")
    if not txns:
        raise HTTPException(422, "No transactions detected in CSV — check column headers.")
    return await ingest(db, user.id, account, txns, source="csv")


@router.post("/import/{account_id}/csv", response_model=ImportReport)
async def import_csv_path(account_id: uuid.UUID, file: UploadFile = File(...),
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    return await _handle_csv_import(account_id, file, user, db)


@router.post("/transactions/import/csv", response_model=ImportReport)
async def import_csv_query(account_id: uuid.UUID = Query(...), file: UploadFile = File(...),
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    return await _handle_csv_import(account_id, file, user, db)


async def _handle_ofx_import(account_id: uuid.UUID, file: UploadFile, user: User, db: AsyncSession):
    account = await _own_account(db, user, account_id)
    content = await file.read()
    try:
        txns = parse_ofx(content)
    except Exception as exc:
        raise HTTPException(400, f"OFX parse failed: {exc}")
    if not txns:
        raise HTTPException(422, "No transactions found in OFX file.")
    return await ingest(db, user.id, account, txns, source="ofx")


@router.post("/import/{account_id}/ofx", response_model=ImportReport)
async def import_ofx_path(account_id: uuid.UUID, file: UploadFile = File(...),
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    return await _handle_ofx_import(account_id, file, user, db)


@router.post("/transactions/import/ofx", response_model=ImportReport)
async def import_ofx_query(account_id: uuid.UUID = Query(...), file: UploadFile = File(...),
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    return await _handle_ofx_import(account_id, file, user, db)


@router.post("/receipts/scan")
@router.post("/ocr/receipt")
async def scan_receipt(file: UploadFile = File(...),
                       user: User = Depends(get_current_user)):
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "Receipt image too large (max 8MB)")
    try:
        parsed = await ocr_receipt(content, mime=file.content_type or "image/jpeg")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return parsed
