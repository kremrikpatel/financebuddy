from datetime import date, timedelta

from app.services.subscriptions import (
    detect_duplicate_charges,
    detect_subscriptions,
    find_duplicate_subscriptions,
)


def _txn(merchant, day, amount=-1500):
    return {"merchant_norm": merchant, "amount_minor": amount,
            "currency": "USD", "date": date(2026, 1, 1) + timedelta(days=day)}


def test_detects_monthly_subscription():
    txns = [_txn("netflix", d * 30, -1699) for d in range(6)]
    subs = detect_subscriptions(txns)
    assert len(subs) == 1
    assert subs[0].cadence_days in (28, 30, 31)
    assert subs[0].avg_amount_minor == 1699


def test_random_spending_not_subscription():
    import random

    random.seed(7)
    txns = [_txn("woolworths", random.randint(0, 180), -random.randint(2000, 20000))
            for _ in range(20)]
    assert detect_subscriptions(txns) == []


def test_duplicate_charge_detection():
    t = _txn("starbucks", 10)
    t2 = _txn("starbucks", 11)
    flagged = detect_duplicate_charges([t, t2])
    assert len(flagged) == 1
    assert flagged[0]["gap_days"] == 1


def test_duplicate_subscription_pairs():
    subs = [
        {"merchant_norm": "spotify", "avg_amount_minor": 1499, "cadence_days": 30},
        {"merchant_norm": "spotfy premium", "avg_amount_minor": 1499, "cadence_days": 30},
        {"merchant_norm": "netflix", "avg_amount_minor": 1699, "cadence_days": 30},
    ]
    pairs = find_duplicate_subscriptions(subs)
    assert (0, 1) in pairs
