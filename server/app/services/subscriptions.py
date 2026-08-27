"""Recurring subscription detection + duplicate subscription/charge detection.

Cadence clustering: groups of same-merchant txns whose gaps cluster around
7 / 14 / 28-31 days with stable amounts (±10%).
Duplicates: near-identical merchants charging similar amounts in the same
window (double-billing, forgotten trial conversions).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from difflib import SequenceMatcher

CADENCE_CANDIDATES = [7, 14, 28, 30, 31, 90, 365]
AMOUNT_TOLERANCE = 0.10


@dataclass
class DetectedSubscription:
    merchant_norm: str
    display_name: str
    cadence_days: int
    avg_amount_minor: int
    currency: str
    first_seen: date
    last_seen: date
    next_expected: date | None
    occurrence_count: int
    confidence: float


def _cluster_cadence(dates: list[date]) -> tuple[int, float] | None:
    """Return (cadence_days, consistency 0..1) or None."""
    if len(dates) < 3:
        return None
    gaps = [(b - a).days for a, b in zip(sorted(dates), sorted(dates)[1:])]
    mean_gap = sum(gaps) / len(gaps)
    best: tuple[int, float] | None = None
    for cand in CADENCE_CANDIDATES:
        tol = max(2, cand * 0.15)
        hits = sum(1 for g in gaps if abs(g - cand) <= tol)
        consistency = hits / len(gaps)
        if consistency >= 0.6 and (best is None or consistency > best[1]):
            best = (cand, consistency)
    # also handle irregular-but-stable custom cadence (~mean_gap, low variance)
    if best is None and mean_gap >= 5:
        variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
        if variance <= 4 and len(gaps) >= 3:
            best = (int(round(mean_gap)), 0.65)
    return best


def detect_subscriptions(txns: list[dict]) -> list[DetectedSubscription]:
    """txns: [{merchant_norm, amount_minor, currency, date}] — expenses only."""
    by_merchant: dict[str, list[dict]] = {}
    for t in txns:
        if t["amount_minor"] >= 0:
            continue
        key = t["merchant_norm"].lower()
        by_merchant.setdefault(key, []).append(t)

    out: list[DetectedSubscription] = []
    today = date.today()
    for key, group in by_merchant.items():
        amounts = [abs(t["amount_minor"]) for t in group]
        med = sorted(amounts)[len(amounts) // 2]
        stable = [t for t in group if abs(abs(t["amount_minor"]) - med) <= med * AMOUNT_TOLERANCE + 100]
        dates = sorted(t["date"] for t in stable)
        cluster = _cluster_cadence(dates)
        if not cluster or len(stable) < 3:
            continue
        cadence, consistency = cluster
        avg_amount = round(sum(abs(t["amount_minor"]) for t in stable) / len(stable))
        last = dates[-1]
        out.append(DetectedSubscription(
            merchant_norm=key, display_name=stable[-1].get("display_name", key),
            cadence_days=cadence, avg_amount_minor=avg_amount,
            currency=stable[-1].get("currency", "USD"),
            first_seen=dates[0], last_seen=last,
            next_expected=last + timedelta(days=cadence) if last + timedelta(days=cadence * 1.5) >= today else None,
            occurrence_count=len(stable), confidence=round(min(consistency, 0.99), 2),
        ))
    return sorted(out, key=lambda s: -s.avg_amount_minor)


def find_duplicate_subscriptions(subs: list[dict], similarity_threshold: float = 0.82) -> list[tuple[int, int]]:
    """subs: serialized subscription dicts → index pairs likely duplicates.
    Strong amount+cadence match lowers the name bar (handles typos/branding variants)."""
    pairs: list[tuple[int, int]] = []
    for i in range(len(subs)):
        for j in range(i + 1, len(subs)):
            a, b = subs[i], subs[j]
            name_sim = SequenceMatcher(None, a["merchant_norm"], b["merchant_norm"]).ratio()
            amt_close = abs(a["avg_amount_minor"] - b["avg_amount_minor"]) <= max(
                a["avg_amount_minor"], b["avg_amount_minor"]) * 0.05
            cadence_close = abs(a["cadence_days"] - b["cadence_days"]) <= 3
            strong_signal = amt_close and cadence_close
            if (strong_signal and name_sim >= similarity_threshold * 0.65) or \
               (name_sim >= similarity_threshold and amt_close):
                pairs.append((i, j))
    return pairs


def detect_duplicate_charges(txns: list[dict], window_days: int = 5) -> list[dict]:
    """Same merchant+amount within a short window → suspicious double charge."""
    flagged: list[dict] = []
    seen: dict[tuple[str, int, str], dict | None] = {}
    ordered = sorted(txns, key=lambda t: t["date"])
    for i, t in enumerate(ordered):
        key = (t.get("merchant_norm", ""), abs(t["amount_minor"]), t.get("currency", "USD"))
        prior = seen.get(key)
        if prior is None:
            seen[key] = t
            continue
        gap_days = (t["date"] - prior["date"]).days
        if 0 < gap_days <= window_days:
            flagged.append({
                "original": {"id": str(prior.get("id")), "date": prior["date"].isoformat()},
                "suspect": {"id": str(t.get("id")), "date": t["date"].isoformat()},
                "gap_days": gap_days,
                "amount_minor": abs(t["amount_minor"]),
                "merchant": t.get("merchant_norm"),
            })
            seen[key] = t  # allow chains (3 identical charges)
    return flagged
