from app.services.goals_debt import compare_strategies, goal_on_track, simulate_payoff


def _debts():
    return [
        {"name": "Card", "principal_minor": 500_000, "apr_bps": 1999, "min_payment_minor": 25_000},
        {"name": "Loan", "principal_minor": 1_000_000, "apr_bps": 899, "min_payment_minor": 40_000},
    ]


def test_payoff_completes():
    plan = simulate_payoff(_debts(), extra_payment_minor=20_000, strategy="avalanche")
    assert all(b == 0 for b in plan["schedule"][-1]["balances"].values())
    assert set(plan["payoff_order"]) == {"Card", "Loan"}


def test_avalanche_saves_interest():
    cmp = compare_strategies(_debts(), extra_payment_minor=20_000)
    assert cmp["interest_saved_by_avalanche_minor"] >= 0


def test_goal_on_track_percent_income():
    result = goal_on_track("percent_income", saved_minor=100_000, target_minor=500_000,
                           monthly_amount_minor=0, percent_of_income=10.0,
                           avg_monthly_income_minor=600_000, target_date=None)
    assert result["effective_monthly_minor"] == 60_000
    assert result["on_track"]
