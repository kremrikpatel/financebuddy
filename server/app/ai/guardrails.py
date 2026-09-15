"""AI Security Guardrails & Sliding-Window Rate Limiting.

Provides:
- Sliding-window rate limiter (30 requests/minute per user).
- Content filter detecting prompt injection attacks, SQL injections, and system overrides.
- Financial domain relevance guardrail redirecting non-financial queries.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import re
import time
import uuid

from fastapi import HTTPException, status


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str | None = None
    redirection_message: str | None = None
    category: str = "clean"


# ── Prompt Injection & Security Attack Patterns ──────────────────────────

PROMPT_INJECTION_PATTERNS = [
    r"(?i)ignore (all |any )?(previous|prior|above) (instructions|directions|prompts)",
    r"(?i)system prompt (override|reveal|leak|output)",
    r"(?i)output (your |the )?system (instructions|prompt) verbatim",
    r"(?i)you are now (an |a )?unrestricted assistant",
    r"(?i)reveal (db|database|admin|root|system) (credentials|passwords|keys)",
    r"(?i)drop table\s+[a-z0-9_]+",
    r"(?i)select\s+.*\s+from\s+credentials",
    r"(?i)union\s+select\s+",
    r"(?i)jailbreak",
    r"(?i)dan mode",
    r"(?i)disregard (all |any )?prior directives",
]

# ── Financial Keywords (Whitelisted Domains) ────────────────────────────

FINANCIAL_KEYWORDS = [
    r"(?i)\b(spend|spent|spending|budget|budgets|money|cash|dollar|dollars|aud|usd|eur|gbp|\$)\b",
    r"(?i)\b(account|accounts|bank|banking|balance|transaction|transactions|statement|card|credit|debit)\b",
    r"(?i)\b(income|salary|wage|wages|earn|earnings|revenue|profit|loss|expense|expenses|cost|costs)\b",
    r"(?i)\b(tax|taxes|taxation|deduction|deductions|bas|gst|ato|abn|superannuation|super|medicare)\b",
    r"(?i)\b(debt|debts|loan|loans|mortgage|interest|repayment|snowball|avalanche)\b",
    r"(?i)\b(save|saving|savings|invest|investing|investment|investments|stock|stocks|crypto|portfolio|wealth|goal|goals)\b",
    r"(?i)\b(family|household|limit|limits|allowance|subscription|subscriptions|bill|bills|receipt|receipts)\b",
    r"(?i)\b(finance|finances|financial|fund|funds|emergency fund|net worth|cashflow|forecast|forecasting)\b",
    r"(?i)\b(hello|hi|hey|help|greetings|morning|afternoon|evening|how are you|who are you|what can you do)\b",
]

# ── Non-Financial / Off-Topic Triggers ───────────────────────────────────

NON_FINANCIAL_PATTERNS = [
    r"(?i)\b(haiku|poem|poetry|rhyme)\b.*(interstellar|black hole|quantum|galaxy|space|gravity)",
    r"(?i)\b(recipe|bake|baking|cook|cooking)\b.*(cake|pasta|cookie|pizza|bread)",
    r"(?i)\b(who won|score of|game of)\b.*(world cup|super bowl|olympics|nba|premier league)",
    r"(?i)\b(write a story|write an essay|movie review|synopsis of)\b",
]


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter enforcing max requests per window."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._user_requests: dict[str, list[float]] = defaultdict(list)

    def check_limit(self, user_id: str | uuid.UUID) -> tuple[bool, int]:
        key = str(user_id)
        now = time.time()
        cutoff = now - self.window_seconds

        # Prune old timestamps
        timestamps = [ts for ts in self._user_requests[key] if ts > cutoff]
        self._user_requests[key] = timestamps

        if len(timestamps) >= self.max_requests:
            remaining = int(self.window_seconds - (now - timestamps[0]))
            return False, max(1, remaining)

        self._user_requests[key].append(now)
        return True, 0

    def enforce_rate_limit(self, user_id: str | uuid.UUID) -> None:
        allowed, remaining = self.check_limit(user_id)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Please wait {remaining} seconds before sending more AI requests.",
            )


chat_rate_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60)


def check_guardrails(message: str) -> GuardrailResult:
    """Inspect input message for prompt injection attacks and non-financial off-topic queries."""
    clean_msg = message.strip()
    if not clean_msg:
        return GuardrailResult(allowed=True, category="clean")

    # 1. Prompt Injection & Adversarial Attack Check
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, clean_msg):
            return GuardrailResult(
                allowed=False,
                category="prompt_injection",
                reason="Potential prompt injection or system override detected.",
                redirection_message=(
                    "I am FinanceBuddy, an AI financial coach. I cannot process instructions that attempt to "
                    "override system parameters or access restricted information. How may I help you with your finances?"
                ),
            )

    # 2. Explicit Non-Financial Off-Topic Check
    for pattern in NON_FINANCIAL_PATTERNS:
        if re.search(pattern, clean_msg):
            return GuardrailResult(
                allowed=False,
                category="non_financial",
                reason="Request falls outside personal finance and budgeting domain.",
                redirection_message=(
                    "I specialize in personal finance, tax preparation, budgeting, and investment tracking. "
                    "I am unable to assist with non-financial topics like creative writing or general knowledge. "
                    "Feel free to ask questions regarding your accounts, transactions, or financial goals!"
                ),
            )

    # 3. Financial relevance check for longer queries (> 30 chars)
    if len(clean_msg) > 40:
        has_financial_intent = any(re.search(kw, clean_msg) for kw in FINANCIAL_KEYWORDS)
        if not has_financial_intent and ("?" in clean_msg or "tell me" in clean_msg.lower() or "write" in clean_msg.lower()):
            # If completely unrelated to any financial term
            return GuardrailResult(
                allowed=False,
                category="non_financial",
                reason="Query is not related to personal finance.",
                redirection_message=(
                    "I'm designed to help with your personal finances, spending insights, budgets, and tax queries. "
                    "Please ask a finance-related question so I can assist you."
                ),
            )

    return GuardrailResult(allowed=True, category="clean")
