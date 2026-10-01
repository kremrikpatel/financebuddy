"""Direct service routing: intent → the existing agent tool / service, no LLM tool selection.

Tools are reused as-is (`await tool.ainvoke(args)`), so business logic, PII masking and the UI
blocks they emit are identical to the LLM path. Requires set_agent_context() beforehand.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app.ai import tools as t
from app.jev import rules
from app.jev.classifier import Intent
from app.models import Budget
from app.services.budget_engine import envelope_status


@dataclass(frozen=True)
class Routed:
    text: str
    handled_by: str  # jev_rule | jev_service
    route: str  # specialist the LLM would have used; keeps AiEvalLog.route_chosen meaningful


# intent -> (tool, route, accepted params)
SERVICES = {
    "balance": (t.list_accounts, "assistant", ()),
    "spend": (t.spending_summary, "budget", ("days",)),
    "goals": (t.goal_overview, "goals", ()),
    "debts": (t.debt_overview, "coach", ()),
    "alerts": (t.recent_alerts, "fraud", ()),
    "subscriptions": (t.subscriptions_detected, "coach", ()),
    "tax_summary": (t.tax_summary, "tax", ("tax_year",)),
    "deductions": (t.deduction_overview, "tax", ("tax_year",)),
    "gst": (t.gst_report, "tax", ("tax_year", "quarter")),
    "forecast": (t.forecast_cashflow, "coach", ()),
}


async def _budget_rule(intent: Intent) -> Routed | None:
    db, uid = await t.get_db_session(), t.uid()
    budget = await db.scalar(select(Budget).where(
        Budget.user_id == uid, Budget.active.is_(True)).order_by(Budget.start_date.desc()))
    if not budget:
        return Routed("No active budget.", "jev_rule", "budget")
    today = date.today()
    statuses = await envelope_status(db, budget, today.year, today.month)
    text = rules.budget_check(statuses, budget.name, budget.currency, intent.params.get("category"))
    return Routed(text, "jev_rule", "budget") if text else None


async def dispatch(intent: Intent) -> Routed | None:
    if intent.name == "budget":
        return await _budget_rule(intent)

    if intent.name not in SERVICES:
        return None
    tool, route, accepted = SERVICES[intent.name]
    args = {k: v for k, v in intent.params.items() if k in accepted}
    text = await tool.ainvoke(args)

    if intent.name == "spend" and intent.params.get("category"):
        picked = rules.category_spend(text, intent.params["category"], args["days"])
        return Routed(picked, "jev_rule", route) if picked else None
    return Routed(text, "jev_service", route)
