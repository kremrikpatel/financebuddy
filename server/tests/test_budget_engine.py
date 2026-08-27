from datetime import date

from app.services.budget_engine import EnvelopeStatus, check_threshold, month_bounds, zero_based_check


def test_balanced():
    check = zero_based_check([{"allocated_minor": 300}, {"allocated_minor": 700}], 1000)
    assert check["balanced"] and check["unassigned_minor"] == 0


def test_under_assigned():
    check = zero_based_check([{"allocated_minor": 400}], 1000)
    assert not check["balanced"] and check["unassigned_minor"] == 600


def test_over_assigned():
    check = zero_based_check([{"allocated_minor": 1200}], 1000)
    assert not check["balanced"] and check["unassigned_minor"] < 0


def test_month_bounds():
    start, end = month_bounds(2026, 2)
    assert start == date(2026, 2, 1)
    assert end == date(2026, 2, 28)

    start_mar, end_mar = month_bounds(2026, 3)
    assert start_mar == date(2026, 3, 1)
    assert end_mar == date(2026, 3, 31)


def test_check_threshold():
    s1 = EnvelopeStatus(
        envelope_id="env-1", name="Groceries", allocated_minor=10000,
        carry_in_minor=0, spent_minor=8500, remaining_minor=1500,
        pct_used=85.0, overspent=False
    )
    s2 = EnvelopeStatus(
        envelope_id="env-2", name="Rent", allocated_minor=200000,
        carry_in_minor=0, spent_minor=100000, remaining_minor=100000,
        pct_used=50.0, overspent=False
    )
    s3 = EnvelopeStatus(
        envelope_id="env-3", name="Dining", allocated_minor=5000,
        carry_in_minor=0, spent_minor=6000, remaining_minor=-1000,
        pct_used=120.0, overspent=True
    )
    warns = check_threshold([s1, s2, s3])
    assert "env-1" in warns
    assert "env-2" not in warns
    assert "env-3" in warns
