"""Smart categorization engine.

Hybrid pipeline, in confidence order:
  1. Merchant normalization + curated rules (regex/keyword → category)
  2. User-history kNN over pgvector embeddings (learns from user edits)
  3. Global seed-corpus kNN
  4. LLM classification fallback (JSON-structured)
Every confirmed user edit becomes a training example — the model adapts
per-user over time without retraining infrastructure.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Category, Transaction
from app.services.embeddings import embed_texts

log = get_logger("categorizer")

# ── Merchant normalization ──────────────────────────────────────────────

_NOISE_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"\b\d{2}/\d{2}(\d{2})?\b",                    # dates
        r"\b(ref|id|txn|auth|pos|ach|ppd|web|tel|rec|cc|purchase)\W*#?\s*\w+\b",
        r"#\d+", r"\bno\.?\s*\d+", r"\*\d{2,}", r"\bx{3,}\d+", r"\b\w*@\w+\b",
        r"\s{2,}",
    ]
]
_LEGAL_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|limited|gmbh|pty|pvt|corp|co|sa|sas|ag|bv|plc)\b\.?$", re.I)


def normalize_merchant(raw: str) -> str:
    s = raw.strip()
    for pat in _NOISE_PATTERNS:
        s = pat.sub(" ", s)
    s = re.sub(r"[^\w&'’\- ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    prev = None
    while prev != s:
        prev = s
        s = _LEGAL_SUFFIX.sub("", s).strip()
    return s or raw.strip().lower()


# ── Seed rules: (compiled pattern, category name, kind) ────────────────

RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"walmart|target|costco|kroger|aldi|woolworths|coles|iga|rewe|lidl|carrefour", re.I), "Groceries", "expense"),
    (re.compile(r"uber eats|doordash|grubhub|deliveroo|menulog|swiggy|zomato", re.I), "Dining Out", "expense"),
    (re.compile(r"starbucks|mcdonald|kfc|subway|chipotle|domino|pizza|cafe|coffee|restaurant|bistro|diner", re.I), "Dining Out", "expense"),
    (re.compile(r"netflix|spotify|hulu|disney|prime video|hbo|apple\.com/bill|youtube premium|audible", re.I), "Subscriptions", "expense"),
    (re.compile(r"shell|bp |exxonmobil|chevron|petrol|fuel|esso|mobil gas", re.I), "Transport & Fuel", "expense"),
    (re.compile(r"uber(?!\s?eats)|lyft|bolt|ola|opalt|metro|transit|parking|toll", re.I), "Public Transport", "expense"),
    (re.compile(r"rent|landlord|mortgage", re.I), "Housing", "expense"),
    (re.compile(r"electric|gas company|water|utility|internet|broadband|comcast|xfinity|verizon|at&t|telstra|vodafone", re.I), "Utilities & Telecom", "expense"),
    (re.compile(r"amazon|amzn|ebay|etsy|aliexpress|temu|shein", re.I), "Shopping", "expense"),
    (re.compile(r"cvs|walgreens|pharmacy|chemist|priceline", re.I), "Health & Pharmacy", "expense"),
    (re.compile(r"gym|fitness|planet fitness|anytime fitness|yoga", re.I), "Health & Fitness", "expense"),
    (re.compile(r"salary|payroll|direct dep|payslip|wages|income payment", re.I), "Salary", "income"),
    (re.compile(r"interest paid|dividend|coupon", re.I), "Investment Income", "income"),
    (re.compile(r"refund|reversal|cashback", re.I), "Refunds", "income"),
    (re.compile(r"insurance|aami|allianz|geico|progressive|nrma", re.I), "Insurance", "expense"),
    (re.compile(r"atm withdrawal|cash withdrawal|atm ", re.I), "Cash & ATM", "expense"),
    (re.compile(r"paypal transfer|venmo|zelle|square cash|cashapp", re.I), "Transfers", "transfer"),
]


def rule_match(norm_merchant: str) -> tuple[str, float] | None:
    """Returns category name if a confident rule matches."""
    low = norm_merchant.lower()
    for pat, cat, _kind in RULES:
        if pat.search(low):
            return cat, 0.92
    return None


# ── Main entrypoint ─────────────────────────────────────────────────────

async def categorize(db: AsyncSession, user_id, norm_merchant: str,
                     amount_minor: int, is_income: bool,
                     text_for_embedding: str | None = None) -> dict:
    """Returns {category_id, category_name, method, confidence, needs_review}."""
    system_cats = {
        c.name: c for c in (await db.execute(
            select(Category).where(Category.user_id.is_(None)))).scalars().all()
    }
    user_cats = {
        c.name.lower(): c for c in (await db.execute(
            select(Category).where(Category.user_id == user_id))).scalars().all()
    }

    def resolve(name: str) -> Category | None:
        return user_cats.get(name.lower()) or system_cats.get(name)

    # 1. Rules
    hit = rule_match(norm_merchant)
    if hit:
        cat = resolve(hit[0])
        if cat and cat.kind == ("income" if is_income else "expense"):
            return _result(cat, "rule", hit[1], is_income)

    # 2/3. Embedding kNN — user history first, then global corpus
    text = text_for_embedding or f"{norm_merchant}"
    vec = (await embed_texts([text]))[0]
    for scope_confidence, scope_user in ((0.88, user_id), (0.72, None)):
        rows = (await db.execute(
            select(Transaction)
            .where(
                Transaction.embedding.is_not(None),
                Transaction.confirmed_by_user.is_(True),
                Transaction.category_id.is_not(None),
                (Transaction.user_id == scope_user) if scope_user is not None else Transaction.user_id.is_not(None),
                Transaction.is_income == is_income,
            )
            .order_by(Transaction.date.desc())
            .limit(400)
        )).scalars().all()
        best_sim, best_cat = 0.0, None
        qnorm = _norm(vec)
        for t in rows:
            sim = _dot(vec, t.embedding) / (qnorm * _norm(t.embedding) or 1e-9) if t.embedding else 0.0
            if sim > best_sim and t.category_id:
                best_sim, best_cat = sim, t.category_id
        if best_sim >= scope_confidence and best_cat:
            cat = await db.get(Category, best_cat)
            if cat:
                conf = min(0.95, best_sim)
                return _result(cat, "knn", conf, is_income, needs_review=best_sim < 0.8)

    # 4. LLM fallback
    llm_cat = await _llm_classify(norm_merchant, amount_minor, is_income, system_cats)
    if llm_cat:
        cat = resolve(llm_cat)
        if cat:
            return _result(cat, "llm", 0.6, is_income, needs_review=True)

    fallback = "Income" if is_income else "Uncategorized"
    return _result(resolve(fallback), "seed", 0.1, is_income, needs_review=True)


def _result(cat: Category | None, method: str, conf: float, is_income: bool,
            needs_review: bool = False) -> dict:
    return {
        "category_id": cat.id if cat else None,
        "category_name": cat.name if cat else ("Income" if is_income else "Uncategorized"),
        "method": method,
        "confidence": round(conf, 3),
        "needs_review": needs_review or conf < 0.5,
    }


def _norm(v: list[float]) -> float:
    import math

    return math.sqrt(sum(x * x for x in v)) or 1e-9


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ── Multi-item split heuristics ─────────────────────────────────────────

_SPLIT_HINTS = re.compile(
    r"\band\b|\+|&|;|\balso\b|\bequals?\b|\btotal\b.*\bitems\b|\d+\s*(x|@)", re.I)


def looks_multi_item(description: str | None, merchant_raw: str) -> bool:
    text = f"{merchant_raw} {description or ''}"
    amounts = re.findall(r"\$?\d+\.\d{2}\b", text)
    return bool(_SPLIT_HINTS.search(text)) or len(amounts) >= 2


async def _llm_classify(norm_merchant: str, amount_minor: int,
                        is_income: bool, candidates: dict[str, Category] | list[str] | set[str]) -> str | None:
    try:
        from app.ai.llm_router import complete_json

        if isinstance(candidates, dict):
            names = sorted(candidates.keys())[:40]
        else:
            names = sorted(list(candidates))[:40]
        prompt = (
            "Classify this bank transaction into exactly one category from the list.\n"
            f"Merchant: {norm_merchant}\n"
            f"Amount: {amount_minor / 100:.2f} (negative=spend, positive=receive); income={is_income}\n"
            f"Categories: {', '.join(names)}\n"
            'Reply JSON only: {"category": "<name>"}'
        )
        data = await complete_json(prompt)
        cat = (data or {}).get("category")
        if isinstance(cat, str):
            for n in names:
                if n.lower() == cat.lower():
                    return n
    except Exception as exc:
        log.warning("llm_classify_failed", error=str(exc))
    return None
