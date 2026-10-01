"""Deterministic intent classifier — regex/keyword only, never calls an LLM.

Returns an Intent only for short, single-purpose lookup questions. Anything advice-shaped,
action-shaped, a thread follow-up, or matching more than one intent returns None so the
request falls through to the LLM unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

MAX_QUESTION_CHARS = 160

# Words that signal reasoning, advice or a data change: always the LLM's job.
_FALLTHROUGH = re.compile(
    r"\b(should|why|how (can|could|do|should|would) i|help|recommend|advice|advise|suggest|plan|"
    r"improve|reduce|cut|best|what if|explain|worth|afford|tips?|strategy|create|add|set ?up|make|"
    r"change|move|recategori[sz]e|propose|cancel|pay off first|compare to|instead)\b",
    re.IGNORECASE,
)
_FOLLOW_UP = re.compile(r"^\s*(and|also|what about|how about|same|ok|okay|then)\b", re.IGNORECASE)

# intent -> pattern. Order is irrelevant: more than one hit means ambiguous.
PATTERNS: dict[str, re.Pattern[str]] = {
    "balance": re.compile(
        r"\b(account balances?|my balances?|balance of my accounts|net worth|"
        r"how much (money )?do i have|(list|show)( me)?( my)? accounts|what accounts)\b", re.IGNORECASE),
    "spend": re.compile(
        r"\b(how much (did|have) i spen[dt]|what did i spend|spending (summary|breakdown)|"
        r"spend(ing)? by category|total spend(ing)?)\b", re.IGNORECASE),
    "budget": re.compile(
        r"\b(am i over( my)? budget|over budget|budget status|how('?s| is) my budget|"
        r"overspen(d|t|ding)|(how much|what'?s|what is) (is )?left in|remaining in|"
        r"close to (my )?(budget )?limit|near(ing)? (my )?(budget )?limit)\b", re.IGNORECASE),
    "goals": re.compile(
        r"\b(goal progress|my (savings )?goals|how are my goals|goals? status|progress on my goals)\b", re.IGNORECASE),
    "debts": re.compile(
        r"\b(my debts|debt (overview|summary|status)|list( my)? debts|"
        r"avalanche (vs\.?|or|versus) snowball|snowball (vs\.?|or|versus) avalanche)\b", re.IGNORECASE),
    "alerts": re.compile(r"\b(alerts?)\b", re.IGNORECASE),
    "subscriptions": re.compile(r"\b(subscriptions?|recurring (charges|payments))\b", re.IGNORECASE),
    "tax_summary": re.compile(
        r"\b((estimated|my) (income )?tax( (estimate|summary|liability|bill))?|"
        r"tax (estimate|summary|liability|bill)|how much tax)\b", re.IGNORECASE),
    "deductions": re.compile(r"\b(my deductions|deductions? (summary|overview|breakdown)|list( my)? deductions)\b", re.IGNORECASE),
    "gst": re.compile(r"\b(gst|bas)\b", re.IGNORECASE),
    "forecast": re.compile(r"\b(cash ?flow forecast|forecast( my)? cash ?flow|runway)\b", re.IGNORECASE),
}

_DAYS = re.compile(r"\b(?:last|past) (\d{1,3}) days?\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d{2})\b")
_QUARTER = re.compile(r"\bq([1-4])\b|\bquarter ([1-4])\b", re.IGNORECASE)
# "on groceries", "in dining" — stops before a period phrase or the end of the question.
_CATEGORY = re.compile(
    r"\b(?:on|in|for) (?:my |the )?([a-z][a-z &'-]{1,40}?)(?:\s+(?:budget|envelope|category))?"
    r"(?=\s+(?:this|last|past|in the|over|so far)\b|[?.!]|$)", re.IGNORECASE)
_NOT_CATEGORIES = {"budget", "month", "week", "year", "total", "envelope", "envelopes", "budgets"}


@dataclass(frozen=True)
class Intent:
    name: str
    confidence: float
    params: dict = field(default_factory=dict)


def _days(q: str) -> tuple[int | None, bool]:
    """Return (days, understood). 'last month' is a calendar month the tools cannot express."""
    if m := _DAYS.search(q):
        return min(int(m.group(1)), 365), True
    low = q.lower()
    if "last month" in low or "last year" in low:
        return None, False
    if "this month" in low:
        return date.today().day, True
    if "this week" in low:
        return 7, True
    if "this year" in low:
        return min(date.today().timetuple().tm_yday, 365), True
    return None, True


def _category(q: str) -> str | None:
    m = _CATEGORY.search(q)
    if not m:
        return None
    cat = m.group(1).strip().lower()
    return None if cat in _NOT_CATEGORIES else cat


def classify(question: str) -> Intent | None:
    q = (question or "").strip()
    if not q or len(q) > MAX_QUESTION_CHARS:
        return None
    if _FALLTHROUGH.search(q) or _FOLLOW_UP.search(q):
        return None

    hits = [name for name, pat in PATTERNS.items() if pat.search(q)]
    if len(hits) != 1:
        return None
    name = hits[0]
    params: dict = {}
    confidence = 0.95

    if name == "spend":
        days, understood = _days(q)
        if not understood:
            return Intent(name, 0.4)  # a period the tools can't answer exactly → LLM
        params["days"] = days or 30
        if cat := _category(q):
            params["category"] = cat
    elif name == "budget":
        if cat := _category(q):
            params["category"] = cat
    elif name in {"tax_summary", "deductions", "gst"}:
        if m := _YEAR.search(q):
            params["tax_year"] = int(m.group(1))
        if name == "gst":
            if m := _QUARTER.search(q):
                params["quarter"] = int(m.group(1) or m.group(2))
            else:
                confidence = 0.85  # tool defaults to Q1; still a direct report
    return Intent(name, confidence, params)
