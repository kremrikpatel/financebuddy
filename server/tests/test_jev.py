"""JEV layer: classifier, rules, cache units + routing tests proving zero LLM calls when handled."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy import select

from app import jev
from app.ai.graph import stream_chat
from app.ai.llm_router import FallbackChatModel
from app.ai.tools import new_collector
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.jev import cache, rules
from app.jev.classifier import classify
from app.models import Account, Budget, BudgetEnvelope, Category, Debt, Goal, Transaction, User
from app.models.ai import AiEvalLog
from app.services.budget_engine import EnvelopeStatus
from app.services.events import bus, new_event

API = "/api/v1"


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    cache.clear()
    monkeypatch.setattr(settings, "jev_enabled", True)
    yield
    cache.clear()


@pytest.fixture
def llm_calls(monkeypatch) -> list[str]:
    """Spy on every LLM entry point (router JSON, specialist generate, streaming)."""
    calls: list[str] = []
    orig_gen, orig_stream = FallbackChatModel._agenerate, FallbackChatModel._astream

    async def gen(self, *a, **k):
        calls.append("generate")
        return await orig_gen(self, *a, **k)

    async def stream(self, *a, **k):
        calls.append("stream")
        async for chunk in orig_stream(self, *a, **k):
            yield chunk

    monkeypatch.setattr(FallbackChatModel, "_agenerate", gen)
    monkeypatch.setattr(FallbackChatModel, "_astream", stream)
    return calls


@pytest.fixture
async def fin_user(db_session):
    """Isolated user with an account, an over-spent envelope, a goal and a debt."""
    user = User(email=f"jev-{uuid.uuid4().hex[:8]}@example.com", password_hash=hash_password("x" * 12),
                full_name="Jev User", locale="en", base_currency="USD", is_active=True)
    db_session.add(user)
    await db_session.flush()
    cat = await db_session.scalar(select(Category).where(
        Category.user_id.is_(None), Category.kind == "expense").limit(1))
    acct = Account(user_id=user.id, name="Jev Checking", type="depository", subtype="checking",
                   currency="USD", balance_minor=123456, is_manual=True)
    db_session.add(acct)
    await db_session.flush()
    db_session.add(Transaction(account_id=acct.id, user_id=user.id, date=date.today(), amount_minor=-5000,
                               currency="USD", merchant_raw="Shop", merchant_norm="shop", category_id=cat.id))
    budget = Budget(user_id=user.id, name="Monthly", start_date=date.today().replace(day=1), currency="USD")
    db_session.add(budget)
    await db_session.flush()
    db_session.add(BudgetEnvelope(budget_id=budget.id, category_id=cat.id, name=cat.name, allocated_minor=3000))
    db_session.add(Goal(user_id=user.id, name="Holiday", target_minor=100000, saved_minor=25000))
    db_session.add(Debt(user_id=user.id, name="Visa", principal_minor=200000, apr_bps=1999, min_payment_minor=5000))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    return user, headers, cat


async def _send(client, headers, message: str) -> dict:
    res = await client.post(f"{API}/chat/send", headers=headers, json={"message": message})
    assert res.status_code == 200, res.text
    return res.json()["reply"]


# ── Classifier ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("question,intent", [
    ("What is my account balance?", "balance"),
    ("How much did I spend?", "spend"),
    ("Am I over budget?", "budget"),
    ("How much is left in dining?", "budget"),
    ("Show my goals", "goals"),
    ("Avalanche vs snowball", "debts"),
    ("Any alerts?", "alerts"),
    ("List my subscriptions", "subscriptions"),
    ("My tax estimate for 2026", "tax_summary"),
    ("Show my deductions", "deductions"),
    ("GST Q2 2026", "gst"),
    ("Forecast my cash flow", "forecast"),
])
def test_classifier_matches_lookup_intents(question, intent):
    result = classify(question)
    assert result is not None and result.name == intent and result.confidence >= 0.8


@pytest.mark.parametrize("question", [
    "Should I pay off my credit card first?",       # advice
    "How can I save more each month?",              # open-ended
    "Why is my spending so high?",                  # reasoning
    "What about last month?",                       # thread follow-up
    "Tell me about index funds",                    # general knowledge
    "Create a budget for groceries",                # action → propose_* tools
    "How much did I spend on food and what is my balance?",  # two intents
    "",
])
def test_classifier_refuses_non_deterministic_questions(question):
    assert classify(question) is None


def test_classifier_parses_params_and_flags_unanswerable_period():
    assert classify("How much did I spend on groceries in the last 14 days?").params == \
        {"days": 14, "category": "groceries"}
    assert classify("GST Q3 2025").params == {"tax_year": 2025, "quarter": 3}
    assert classify("How much did I spend last month?").confidence < 0.8  # calendar month → LLM


# ── Rules engine ────────────────────────────────────────────────────────

def _env(name, alloc, spent, eid="e"):
    return EnvelopeStatus(envelope_id=eid + name, name=name, allocated_minor=alloc, carry_in_minor=0,
                          spent_minor=spent,
                          remaining_minor=alloc - spent, pct_used=round(spent / alloc * 100, 1),
                          overspent=spent > alloc)


def test_budget_rule_reports_over_and_near_limit_envelopes():
    text = rules.budget_check([_env("Dining", 10000, 12000), _env("Groceries", 10000, 8500),
                               _env("Fun", 10000, 1000)], "Monthly", "USD")
    assert "Dining: over by 20.00 USD" in text
    assert "Groceries: 15.00 USD left" in text  # ≥80% threshold from budget_engine.check_threshold
    assert "Fun" not in text


def test_budget_rule_single_envelope_and_unknown_category_falls_through():
    statuses = [_env("Dining", 10000, 4000)]
    assert "Dining: 60.00 USD left" in rules.budget_check(statuses, "M", "USD", "dining")
    assert rules.budget_check(statuses, "M", "USD", "travel") is None
    assert "within budget" in rules.budget_check(statuses, "M", "USD")


def test_category_spend_rule_picks_one_line():
    summary = "Spend last 30d — total 80.00:\n- Groceries: 50.00\n- Dining Out: 30.00"
    assert rules.category_spend(summary, "groceries", 30) == "You spent 50.00 on Groceries in the last 30 days."
    assert "No spending recorded" in rules.category_spend(summary, "travel", 30)


# ── Cache ───────────────────────────────────────────────────────────────

def test_cache_hit_expiry_and_invalidation(monkeypatch):
    k = cache.key("u1", "balance", {})
    cache.put(k, "answer", [{"type": "x"}], "jev_service", "assistant", ttl_seconds=60)
    assert cache.get(k).text == "answer"

    cache.invalidate("u2")
    assert cache.get(k) is not None  # other users don't affect this entry
    cache.invalidate("u1")
    assert cache.get(k) is None  # data changed → stale entry dropped

    cache.put(k, "answer", [], "jev_service", "assistant", ttl_seconds=-1)
    assert cache.get(k) is None  # expired


# ── Routing: JEV-handled intents never call the LLM ─────────────────────

async def test_balance_lookup_is_served_by_service_without_llm(async_client, fin_user, llm_calls, db_session):
    _user, headers, _ = fin_user
    reply = await _send(async_client, headers, "What is my account balance?")
    assert reply["provider"] == "jev_service"
    assert "Jev Checking" in reply["content"] and "1234.56" in reply["content"]
    assert llm_calls == []
    log = await db_session.scalar(select(AiEvalLog).where(AiEvalLog.message_id == uuid.UUID(reply["id"])))
    assert log.provider_used == "jev_service" and log.tokens_in == 0 and log.tokens_out == 0


async def test_budget_limit_check_is_served_by_rule_without_llm(async_client, fin_user, llm_calls):
    _user, headers, cat = fin_user
    reply = await _send(async_client, headers, "Am I over budget?")
    assert reply["provider"] == "jev_rule"
    assert f"{cat.name}: over by 20.00 USD" in reply["content"]
    assert llm_calls == []


async def test_category_spend_is_served_by_rule_without_llm(async_client, fin_user, llm_calls):
    _user, headers, cat = fin_user
    reply = await _send(async_client, headers, f"How much did I spend on {cat.name}?")
    assert reply["provider"] == "jev_rule"
    assert reply["content"] == f"You spent 50.00 on {cat.name} in the last 30 days."
    assert reply["blocks"]  # spending_summary's chart card still reaches the UI
    assert llm_calls == []


@pytest.mark.parametrize("question,expected", [
    ("Show my goals", "Holiday: 25%"),
    ("Avalanche vs snowball", "Avalanche saves"),
    ("Any alerts?", "No alerts."),
    ("List my subscriptions", "No recurring subscriptions detected."),
    ("Show my deductions for 2026", "No tax deductions recorded"),
    ("Forecast my cash flow", "Need at least 3 months"),
])
async def test_direct_service_intents_skip_llm(async_client, fin_user, llm_calls, question, expected):
    _user, headers, _ = fin_user
    reply = await _send(async_client, headers, question)
    assert reply["provider"] == "jev_service"
    assert expected in reply["content"]
    assert llm_calls == []


async def test_repeat_question_hits_cache_until_data_changes(async_client, fin_user, llm_calls):
    user, headers, _ = fin_user
    first = await _send(async_client, headers, "What is my account balance?")
    second = await _send(async_client, headers, "what is my account balance")
    assert (first["provider"], second["provider"]) == ("jev_service", "jev_cache")
    assert second["content"] == first["content"]

    await bus.publish(new_event("transaction.created", str(user.id), {}))
    third = await _send(async_client, headers, "What is my account balance?")
    assert third["provider"] == "jev_service"
    assert llm_calls == []


async def test_successful_write_request_invalidates_cache(async_client, fin_user):
    _user, headers, _ = fin_user
    await _send(async_client, headers, "Show my goals")
    res = await async_client.post(f"{API}/goals", headers=headers,
                                  json={"name": "Car", "target_minor": 500000, "currency": "USD"})
    assert res.status_code < 400, res.text
    reply = await _send(async_client, headers, "Show my goals")
    assert reply["provider"] == "jev_service" and "Car" in reply["content"]


async def test_stream_path_yields_jev_answer_without_llm(db_session, fin_user, llm_calls):
    user, _headers, _ = fin_user
    events = [ev async for ev in stream_chat([HumanMessage(content="Show my goals")], str(user.id),
                                             str(uuid.uuid4()), db_session=db_session,
                                             collector=new_collector())]
    assert [e["type"] for e in events] == ["delta", "final"]
    assert events[-1]["message"].response_metadata["provider"] == "jev_service"
    assert llm_calls == []


# ── Routing: everything else falls through to the LLM unchanged ─────────

@pytest.mark.parametrize("question", [
    "Should I pay off my credit card or save first?",
    "How can I improve my finances?",
    "Explain how compound interest works",
    "How much did I spend last month?",
])
async def test_ambiguous_or_advice_questions_fall_through_to_llm(async_client, fin_user, llm_calls, question):
    _user, headers, _ = fin_user
    reply = await _send(async_client, headers, question)
    assert reply["provider"] not in jev.HANDLERS
    assert llm_calls  # the existing LangGraph path ran


async def test_unknown_envelope_falls_through_to_llm(async_client, fin_user, llm_calls):
    _user, headers, _ = fin_user
    reply = await _send(async_client, headers, "How much is left in yacht maintenance?")
    assert reply["provider"] not in jev.HANDLERS
    assert llm_calls


async def test_jev_disabled_sends_everything_to_llm(async_client, fin_user, llm_calls, monkeypatch):
    _user, headers, _ = fin_user
    monkeypatch.setattr(settings, "jev_enabled", False)
    reply = await _send(async_client, headers, "What is my account balance?")
    assert reply["provider"] not in jev.HANDLERS
    assert llm_calls


async def test_jev_stats_endpoint_reports_avoided_llm_calls(async_client, fin_user, llm_calls):
    _user, headers, _ = fin_user
    await _send(async_client, headers, "Show my goals")
    await _send(async_client, headers, "How can I improve my finances?")
    stats = (await async_client.get(f"{API}/ai/jev/stats", headers=headers)).json()
    assert stats["total"] == 2
    assert stats["by_handler"]["jev_service"] == 1 and stats["by_handler"]["llm"] == 1
    assert stats["llm_calls_avoided_pct"] == 50.0
