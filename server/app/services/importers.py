"""CSV / OFX import with flexible column mapping and dedup."""
from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

import ofxparse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account
from app.services.txn_service import create_transaction


@dataclass
class ParsedTxn:
    date: date
    amount_minor: int
    merchant_raw: str
    description: str | None = None
    external_id: str | None = None


@dataclass
class ImportReport:
    created: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)


# ── Column detection ────────────────────────────────────────────────────

_DATE_COLS = ["date", "transaction date", "posted", "posting date", "post date", "trans date"]
_AMOUNT_COLS = ["amount", "value", "transaction amount", "amt", "debit"]
_MERCHANT_COLS = ["merchant", "payee", "name", "description", "details", "narrative", "particulars"]
_DESC_COLS = ["description", "memo", "notes", "reference", "narrative"]
_ID_COLS = ["id", "transaction id", "fitid", "ref", "reference"]


def _find(colnames: list[str], candidates: list[str]) -> str | None:
    """Pick the column matching the highest-priority candidate;
    ties break toward file order."""
    low = {c.lower().strip(): c for c in colnames if c}
    best: tuple[int, int] | None = None  # (candidate_rank, column_index)
    result: str | None = None
    for idx, (col, orig) in enumerate(low.items()):
        for rank, cand in enumerate(candidates):
            if cand == col or cand in col:
                if best is None or (rank, idx) < best:
                    best = (rank, idx)
                    result = orig
                break
    return result


def _parse_date(value: str) -> date:
    if not value or not value.strip():
        raise ValueError("Empty date string")
    v = value.strip().split("T")[0].split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d",
                "%d.%m.%Y", "%b %d, %Y", "%d %b %Y", "%Y%m%d", "%m-%d-%Y",
                "%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unparseable date: {value!r}")


def _parse_amount(value: str) -> int:
    if not value or not value.strip():
        return 0
    v = value.strip()
    v_upper = v.upper()
    negative = False
    if v.startswith("(") and v.endswith(")"):
        negative = True
        v = v[1:-1].strip()
    elif v.startswith("-") or "-" in v:
        negative = True
        v = v.replace("-", "").strip()
    elif "DR" in v_upper or "DEBIT" in v_upper:
        negative = True
        v = v_upper.replace("DR", "").replace("DEBIT", "").strip()
    elif "CR" in v_upper or "CREDIT" in v_upper:
        negative = False
        v = v_upper.replace("CR", "").replace("CREDIT", "").strip()

    # Remove currency symbols and whitespace
    for sym in ("$", "€", "£", "¥", "₹", "A$", "C$", "NZ$", "CHF", "USD", "EUR", "GBP", "AUD", "CAD"):
        v = v.replace(sym, "")
    v = v.strip()

    # Handle comma as decimal separator if no dot present e.g. "12,50"
    if "," in v and "." not in v:
        parts = v.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            v = f"{parts[0]}.{parts[1]}"
        else:
            v = v.replace(",", "")
    else:
        v = v.replace(",", "")

    import re
    cleaned = re.sub(r"[^\d.]", "", v)
    if not cleaned:
        return 0
    minor = round(float(cleaned) * 100)
    return -minor if negative else minor


# ── CSV ─────────────────────────────────────────────────────────────────

def parse_csv(content: bytes) -> list[ParsedTxn]:
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|") if (sample.count(",") > 1 or ";" in sample or "\t" in sample) else csv.excel
    except Exception:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = list(reader)
    if not rows:
        return []
    cols = [c for c in rows[0].keys() if c]
    date_col = _find(cols, _DATE_COLS) or (cols[0] if cols else None)
    amt_col = _find(cols, _AMOUNT_COLS)
    debit_col = _find(cols, ["debit", "withdrawal", "spent", "out"])
    credit_col = _find(cols, ["credit", "deposit", "received", "in"])
    merch_col = _find(cols, _MERCHANT_COLS) or (cols[1] if len(cols) > 1 else None)
    desc_col = _find(cols, _DESC_COLS)
    if desc_col == merch_col:
        desc_col = None
    id_col = _find(cols, _ID_COLS)

    out: list[ParsedTxn] = []
    for row in rows:
        try:
            if not date_col or not row.get(date_col):
                continue
            d = _parse_date(row[date_col])
            
            raw_amount = 0
            if amt_col and row.get(amt_col):
                raw_amount = _parse_amount(row[amt_col])
            
            # If amt_col was missing or 0, or debit/credit columns exist:
            if (raw_amount == 0 or not amt_col) and (debit_col or credit_col):
                debit_str = row.get(debit_col, "").strip() if debit_col else ""
                credit_str = row.get(credit_col, "").strip() if credit_col else ""
                if debit_str:
                    raw_amount = -abs(_parse_amount(debit_str))
                elif credit_str:
                    raw_amount = abs(_parse_amount(credit_str))

            merchant = (row.get(merch_col) or "Unknown").strip() if merch_col else "Unknown"
            description = (row.get(desc_col) or "").strip() or None if desc_col else None
            ext_id = row.get(id_col) if id_col else None
            out.append(ParsedTxn(date=d, amount_minor=raw_amount,
                                 merchant_raw=merchant, description=description,
                                 external_id=ext_id))
        except Exception:
            continue
    return out


# ── OFX ─────────────────────────────────────────────────────────────────

def parse_ofx(content: bytes) -> list[ParsedTxn]:
    ofx = ofxparse.OfxParser.parse(io.BytesIO(content))
    out: list[ParsedTxn] = []
    for account in getattr(ofx, "accounts", []):
        statement = getattr(account, "statement", None)
        transactions = getattr(statement, "transactions", []) if statement else []
        for txn in transactions:
            d = txn.date.date() if hasattr(txn.date, "date") else txn.date
            amount = round(float(txn.amount) * 100)
            out.append(ParsedTxn(
                date=d, amount_minor=amount,
                merchant_raw=(txn.payee or txn.memo or "Unknown").strip(),
                description=(txn.memo or "").strip() or None,
                external_id=getattr(txn, "id", None),
            ))
    return out


# ── Ingestion ───────────────────────────────────────────────────────────

async def ingest(db: AsyncSession, user_id: uuid.UUID, account: Account,
                 txns: list[ParsedTxn], source: str) -> ImportReport:
    report = ImportReport()
    for t in txns:
        try:
            _txn, created = await create_transaction(
                db, account=account, date=t.date, amount_minor=t.amount_minor,
                currency=account.currency, merchant_raw=t.merchant_raw,
                description=t.description, source=source, external_id=t.external_id,
            )
            report.created += 1 if created else 0
            report.duplicates += 0 if created else 1
        except Exception as exc:
            report.errors.append(str(exc)[:200])
    return report
