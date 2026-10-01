"""Rules engine: deterministic finance checks over facts the existing services already compute.

Rules are pure functions (no DB, no LLM) so they are trivially testable. Returning None means
"this rule can't answer confidently" and the request falls through to the LLM.
"""
from __future__ import annotations

import re

from app.services.budget_engine import EnvelopeStatus, check_threshold


def _money(minor: int) -> str:
    return f"{minor / 100:.2f}"


def _match(name: str, category: str) -> bool:
    a, b = name.lower(), category.lower()
    return a == b or a.startswith(b) or b.startswith(a)


def budget_check(statuses: list[EnvelopeStatus], budget_name: str, currency: str,
                 category: str | None = None) -> str | None:
    """Over-budget / near-limit check. Thresholds come from budget_engine.check_threshold."""
    if not statuses:
        return f"Budget '{budget_name}' has no envelopes yet."

    if category:
        hits = [s for s in statuses if _match(s.name, category)]
        if len(hits) != 1:
            return None  # unknown or ambiguous envelope → let the LLM ask
        s = hits[0]
        if s.overspent:
            return (f"{s.name}: over budget by {_money(abs(s.remaining_minor))} {currency} "
                    f"(spent {_money(s.spent_minor)} of {_money(s.allocated_minor)}, {s.pct_used}%).")
        return (f"{s.name}: {_money(s.remaining_minor)} {currency} left "
                f"(spent {_money(s.spent_minor)} of {_money(s.allocated_minor)}, {s.pct_used}%).")

    warn_ids = set(check_threshold(statuses))
    over = [s for s in statuses if s.overspent]
    near = [s for s in statuses if s.envelope_id in warn_ids and not s.overspent]
    lines = [f"Budget '{budget_name}' this month:"]
    if over:
        lines.append("Over budget:")
        lines += [f"- {s.name}: over by {_money(abs(s.remaining_minor))} {currency} ({s.pct_used}%)" for s in over]
    if near:
        lines.append("Close to the limit (≥80%):")
        lines += [f"- {s.name}: {_money(s.remaining_minor)} {currency} left ({s.pct_used}%)" for s in near]
    if not over and not near:
        lines.append("All envelopes are within budget.")
    return "\n".join(lines)


_SUMMARY_LINE = re.compile(r"^- (?P<name>.+): (?P<amount>-?\d+(?:\.\d+)?)$")


def category_spend(summary_text: str, category: str, days: int) -> str | None:
    """Pick one category's total out of the spending_summary tool output."""
    # ponytail: parses the tool's own "- Name: 12.34" lines; switch to a shared query helper
    # if spending_summary's text format ever changes.
    hits = []
    for line in summary_text.splitlines():
        m = _SUMMARY_LINE.match(line.strip())
        if m and _match(m.group("name"), category):
            hits.append((m.group("name"), m.group("amount")))
    if len(hits) > 1:
        return None
    if not hits:
        return f"No spending recorded in '{category}' in the last {days} days."
    name, amount = hits[0]
    return f"You spent {amount} on {name} in the last {days} days."
