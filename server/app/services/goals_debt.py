"""Goal strategies & debt payoff simulators.

Goals auto-adjust to income shifts via percent_of_income strategy; the
service recomputes recommended monthly contributions from detected salary.
Debt: snowball (smallest balance first) vs avalanche (highest APR first),
month-by-month amortization with extra payment.
"""
from __future__ import annotations

import math
from datetime import date


# ── Goals ───────────────────────────────────────────────────────────────

def goal_progress(target_minor: int, saved_minor: int) -> dict:
    pct = min(100.0, (saved_minor / target_minor * 100) if target_minor else 0.0)
    remaining = max(0, target_minor - saved_minor)
    return {"pct": round(pct, 1), "remaining_minor": remaining}


def months_to_target(saved: int, monthly: int, target: int) -> int:
    if saved >= target:
        return 0
    if monthly <= 0:
        return math.inf
    return math.ceil((target - saved) / monthly)


def goal_on_track(strategy: str, saved_minor: int, target_minor: int,
                  monthly_amount_minor: int, percent_of_income: float,
                  avg_monthly_income_minor: int, target_date: date | None) -> dict:
    progress = goal_progress(target_minor, saved_minor)
    if strategy == "percent_income" and avg_monthly_income_minor > 0:
        effective_monthly = round(avg_monthly_income_minor * percent_of_income / 100)
    else:
        effective_monthly = monthly_amount_minor
    months_left = months_to_target(saved_minor, effective_monthly, target_minor)
    on_track = True
    note = ""
    if target_date:
        days_left = (target_date - date.today()).days
        months_available = max(days_left / 30.44, 0)
        on_track = months_left <= months_available
        note = f"{months_left} months at current pace vs {months_available:.1f} available"
    elif months_left == math.inf and saved_minor < target_minor:
        on_track = False
        note = "No contribution configured"
    months_val = months_left if months_left != math.inf else None
    return {
        **progress,
        "effective_monthly_minor": effective_monthly,
        "months_to_complete": months_val,
        "months_remaining": months_val,
        "on_track": on_track,
        "note": note,
    }


# ── Debt payoff simulation ──────────────────────────────────────────────

def simulate_payoff(debts: list[dict], extra_payment_minor: int = 0,
                    strategy: str = "avalanche") -> dict:
    """debts: [{name, principal_minor, apr_bps, min_payment_minor}]
    Returns month-by-month schedule, payoff order, total interest."""
    debts = [dict(d) for d in debts if d["principal_minor"] > 0]
    if not debts:
        return {"strategy": strategy, "months": 0, "total_interest_minor": 0,
                "payoff_order": [], "schedule": []}

    order_key = (lambda d: (-d["apr_bps"], d["principal_minor"])) if strategy == "avalanche" \
        else (lambda d: (d["principal_minor"], -d["apr_bps"]))
    schedule: list[dict] = []
    payoff_order: list[str] = []
    total_interest = 0
    month = 0
    budget_extra = extra_payment_minor

    while any(d["principal_minor"] > 0 for d in debts) and month < 600:
        month += 1
        # interest accrual (monthly APR/12)
        month_interest = 0
        for d in debts:
            if d["principal_minor"] > 0:
                i = d["principal_minor"] * (d["apr_bps"] / 10000) / 12
                month_interest += i
                d["principal_minor"] = int(round(d["principal_minor"] + i))
        total_interest += month_interest

        available = sum(d["min_payment_minor"] for d in debts if d["principal_minor"] > 0) + budget_extra

        # pay minimums first
        for d in debts:
            if d["principal_minor"] <= 0:
                continue
            pay = min(d["min_payment_minor"], d["principal_minor"])
            d["principal_minor"] -= pay
            available -= pay

        # snowball/avalanche the remainder into priority order
        for d in sorted(debts, key=order_key):
            while available > 0 and d["principal_minor"] > 0:
                pay = min(available, d["principal_minor"])
                d["principal_minor"] -= pay
                available -= pay
                break

        newly_paid = [d["name"] for d in debts if d["principal_minor"] == 0 and d["name"] not in payoff_order]
        payoff_order.extend(newly_paid)
        schedule.append({
            "month": month,
            "balances": {d["name"]: d["principal_minor"] for d in debts},
            "interest_minor": int(round(month_interest)),
        })

    # Calculate estimated debt-free date
    from datetime import timedelta
    today = date.today()
    # approx 30.44 days per month
    debt_free_date = (today + timedelta(days=int(month * 30.44))).isoformat() if month > 0 else today.isoformat()
    total_min_payments = sum(d["min_payment_minor"] for d in debts)

    return {
        "strategy": strategy,
        "months": month,
        "monthly_payment_minor": total_min_payments + extra_payment_minor,
        "total_interest_minor": int(round(total_interest)),
        "debt_free_date": debt_free_date,
        "payoff_order": payoff_order,
        "schedule": schedule[:120],
    }


def compare_strategies(debts: list[dict], extra_payment_minor: int = 0) -> dict:
    avalanche = simulate_payoff(debts, extra_payment_minor, "avalanche")
    snowball = simulate_payoff(debts, extra_payment_minor, "snowball")
    return {
        "avalanche": avalanche,
        "snowball": snowball,
        "interest_saved_by_avalanche_minor":
            snowball["total_interest_minor"] - avalanche["total_interest_minor"],
        "months_saved_by_avalanche": snowball["months"] - avalanche["months"],
    }
