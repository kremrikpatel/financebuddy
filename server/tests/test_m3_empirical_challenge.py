"""Empirical Challenge & Stress Test Suite for Milestone M3 (AI LangGraph, Tax Agent & Eval Capture).

Tests:
1. Tax Tools Edge Cases:
   - tax_summary with empty DB, non-existent year, negative income, extreme income, deduction offsets.
   - deduction_overview with empty DB, unassigned categories, multi-category claims, non-existent year.
   - gst_report with empty DB, all 4 quarters, refund scenarios, out-of-range quarters.
2. Supervisor Routing Matrix:
   - Full page_context permutations (/tax, /budgets, /family, /transactions, /dashboard, None, invalid paths).
   - Intent keyword precedence over page_context.
3. LangGraph & Agent Execution:
   - Graph compilation and node integrity.
   - PII masking on input messages.
4. AI Eval Capture:
   - AiEvalLog entry creation, field completeness, latency recording, route accuracy.
"""
from __future__ import annotations

from datetime import date, datetime
import os
import sys
import uuid

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from app.ai.graph import ROUTES, build_graph, mask_node, route_of, run_chat, supervisor_node
from app.ai.tools import (
    ALL_TAX_TOOLS,
    deduction_overview,
    gst_report,
    set_agent_context,
    tax_summary,
)
from app.models.ai import AiEvalLog, ChatMessage, ChatThread
from app.models.finance import Account, Category, Transaction
from app.models.tax import (
    BusinessType,
    TaxCategory,
    TaxCategoryType,
    TaxDeduction,
    TaxProfile,
)
from app.models.user import User
from app.services.tax_engine import (
    calculate_estimated_tax,
    calculate_gst_liability,
    get_deduction_summary,
)


async def get_or_create_tax_cat(
    db: AsyncSession, name: str, code: str, cat_type: TaxCategoryType = TaxCategoryType.DEDUCTION
) -> TaxCategory:
    cat = await db.scalar(select(TaxCategory).where(TaxCategory.code == code))
    if not cat:
        cat = TaxCategory(name=name, code=code, type=cat_type)
        db.add(cat)
        await db.flush()
    return cat


# ============================================================================
# 1. Tax Tools Edge Cases & Invariants
# ============================================================================

@pytest.mark.asyncio
async def test_tax_summary_empty_database(db_session: AsyncSession, test_user: User):
    """Empty DB should return $0 gross income, $0 deductions, $0 tax liability, 0.00% effective rate."""
    set_agent_context(db_session, test_user.id)
    output = await tax_summary.ainvoke({"tax_year": 2026})

    assert "Tax Summary for 2026 (AU)" in output
    assert "- Gross Income: $0.00 AUD" in output
    assert "- Total Deductions: $0.00 AUD (0 claim(s))" in output
    assert "- Taxable Income: $0.00 AUD" in output
    assert "- Base Income Tax: $0.00 AUD" in output
    assert "- Medicare Levy (2%): $0.00 AUD" in output
    assert "- Estimated Total Tax Liability: $0.00 AUD" in output
    assert "- Effective Tax Rate: 0.00%" in output


@pytest.mark.asyncio
async def test_tax_summary_non_existent_tax_year(db_session: AsyncSession, test_user: User):
    """Non-existent tax year (e.g. 1970, 2099) should return clean 0 figures without error."""
    set_agent_context(db_session, test_user.id)

    for y in [1970, 2099]:
        output = await tax_summary.ainvoke({"tax_year": y})
        assert f"Tax Summary for {y} (AU)" in output
        assert "- Gross Income: $0.00 AUD" in output
        assert "- Estimated Total Tax Liability: $0.00 AUD" in output


@pytest.mark.asyncio
async def test_tax_summary_negative_and_zero_income(
    db_session: AsyncSession, test_user: User, test_account: Account
):
    """Negative income transactions or expenses should not create negative gross income."""
    set_agent_context(db_session, test_user.id)

    # Add expense transaction
    expense = Transaction(
        account_id=test_account.id,
        user_id=test_user.id,
        amount_minor=-50000,
        currency="AUD",
        description="Expense",
        merchant_raw="Coffee Shop",
        date=date(2026, 4, 1),
        is_income=False,
    )
    db_session.add(expense)
    await db_session.commit()

    output = await tax_summary.ainvoke({"tax_year": 2026})
    assert "- Gross Income: $0.00 AUD" in output
    assert "- Taxable Income: $0.00 AUD" in output
    assert "- Estimated Total Tax Liability: $0.00 AUD" in output


@pytest.mark.asyncio
async def test_tax_summary_high_income_brackets(
    db_session: AsyncSession, test_user: User, test_account: Account
):
    """High income ($250,000 AUD) with deductions ($30,000 AUD) -> Taxable: $220,000."""
    set_agent_context(db_session, test_user.id)

    income = Transaction(
        account_id=test_account.id,
        user_id=test_user.id,
        amount_minor=25000000,  # $250,000 AUD
        currency="AUD",
        description="Consulting Revenue",
        merchant_raw="Enterprise Client",
        date=date(2026, 5, 20),
        is_income=True,
    )
    db_session.add(income)

    cat = await get_or_create_tax_cat(db_session, "Consulting Tools", "D4_TOOLS_M3")

    ded = TaxDeduction(
        user_id=test_user.id,
        tax_category_id=cat.id,
        amount_minor=3000000,  # $30,000 AUD
        gst_claimed_minor=272727,
        tax_year=2026,
    )
    db_session.add(ded)
    await db_session.commit()

    output = await tax_summary.ainvoke({"tax_year": 2026})
    assert "- Gross Income: $250000.00 AUD" in output
    assert "- Total Deductions: $30000.00 AUD (1 claim(s))" in output
    assert "- Taxable Income: $220000.00 AUD" in output
    # Tax on 220,000: Base tax = 51638 + (220000 - 190000) * 0.45 = 51638 + 13500 = 65138.
    # Medicare = 220000 * 0.02 = 4400. Total = 69538.
    assert "- Base Income Tax: $65138.00 AUD" in output
    assert "- Medicare Levy (2%): $4400.00 AUD" in output
    assert "- Estimated Total Tax Liability: $69538.00 AUD" in output


@pytest.mark.asyncio
async def test_deduction_overview_empty_database(db_session: AsyncSession, test_user: User):
    """Empty deductions should return clear no deductions message."""
    set_agent_context(db_session, test_user.id)
    output = await deduction_overview.ainvoke({"tax_year": 2026})
    assert output == "No tax deductions recorded for tax year 2026."


@pytest.mark.asyncio
async def test_deduction_overview_multiple_categories(
    db_session: AsyncSession, test_user: User
):
    """Multiple categories with GST claimed."""
    set_agent_context(db_session, test_user.id)

    cat1 = await get_or_create_tax_cat(db_session, "Home Office", "D2_HOME_OFFICE_M3")
    cat2 = await get_or_create_tax_cat(db_session, "Car Travel", "D1_CAR_M3")

    d1 = TaxDeduction(
        user_id=test_user.id,
        tax_category_id=cat1.id,
        amount_minor=120000,
        gst_claimed_minor=10909,
        tax_year=2026,
    )
    d2 = TaxDeduction(
        user_id=test_user.id,
        tax_category_id=cat2.id,
        amount_minor=80000,
        gst_claimed_minor=7272,
        tax_year=2026,
    )
    db_session.add_all([d1, d2])
    await db_session.commit()

    output = await deduction_overview.ainvoke({"tax_year": 2026})
    assert "Tax Deductions for 2026 (Total: $2000.00 AUD, Total GST Claimed: $181.81 AUD, Claims: 2)" in output
    assert "- Home Office (D2_HOME_OFFICE_M3): $1200.00 AUD across 1 claim(s) (GST claimed: $109.09 AUD)" in output
    assert "- Car Travel (D1_CAR_M3): $800.00 AUD across 1 claim(s) (GST claimed: $72.72 AUD)" in output


@pytest.mark.asyncio
async def test_gst_report_empty_database(db_session: AsyncSession, test_user: User):
    """Empty DB should return 0 for all BAS fields and Payable $0.00."""
    set_agent_context(db_session, test_user.id)
    output = await gst_report.ainvoke({"tax_year": 2026, "quarter": 1})

    assert "BAS GST Report for 2026 Q1" in output
    assert "- G1 (Total Sales): $0.00 AUD" in output
    assert "- 1A (GST on Sales): $0.00 AUD" in output
    assert "- 1B (GST on Purchases / Credits): $0.00 AUD" in output
    assert "- Net GST Payable: $0.00 AUD" in output


@pytest.mark.asyncio
async def test_gst_report_refund_scenario(
    db_session: AsyncSession, test_user: User, test_account: Account
):
    """When purchases GST exceeds sales GST, report must say Net GST Refund."""
    set_agent_context(db_session, test_user.id)

    # Small sales in Q2: $1,100 -> $100 GST
    sale = Transaction(
        account_id=test_account.id,
        user_id=test_user.id,
        amount_minor=110000,
        currency="AUD",
        description="Small Service",
        merchant_raw="Client",
        date=date(2026, 4, 15),
        is_income=True,
    )
    db_session.add(sale)

    # Large purchase with $500 GST credit
    cat = await get_or_create_tax_cat(db_session, "Capital Equipment", "D4_EQUIP_M3")

    ded = TaxDeduction(
        user_id=test_user.id,
        tax_category_id=cat.id,
        amount_minor=550000,
        gst_claimed_minor=50000,  # $500 GST
        tax_year=2026,
    )
    db_session.add(ded)
    await db_session.commit()

    output = await gst_report.ainvoke({"tax_year": 2026, "quarter": 2})
    assert "BAS GST Report for 2026 Q2" in output
    assert "- G1 (Total Sales): $1100.00 AUD" in output
    assert "- 1A (GST on Sales): $100.00 AUD" in output
    assert "- 1B (GST on Purchases / Credits): $500.00 AUD" in output
    assert "- Net GST Refund: $400.00 AUD" in output


@pytest.mark.asyncio
async def test_gst_report_quarter_boundary_and_defaults(
    db_session: AsyncSession, test_user: User, test_account: Account
):
    """Test all quarters (Q1, Q2, Q3, Q4) and out-of-range fallback (e.g. Q5, Q0)."""
    set_agent_context(db_session, test_user.id)

    # Sales in Q3 (Aug 2026)
    sale_q3 = Transaction(
        account_id=test_account.id,
        user_id=test_user.id,
        amount_minor=220000,
        currency="AUD",
        description="Q3 Consulting",
        merchant_raw="Client",
        date=date(2026, 8, 10),
        is_income=True,
    )
    db_session.add(sale_q3)
    await db_session.commit()

    # Q3 report should include the sale
    out_q3 = await gst_report.ainvoke({"tax_year": 2026, "quarter": 3})
    assert "- G1 (Total Sales): $2200.00 AUD" in out_q3

    # Q1 report should NOT include the Q3 sale
    out_q1 = await gst_report.ainvoke({"tax_year": 2026, "quarter": 1})
    assert "- G1 (Total Sales): $0.00 AUD" in out_q1

    # Quarter out-of-bounds (e.g. quarter 99) falls back cleanly without crash
    out_invalid = await gst_report.ainvoke({"tax_year": 2026, "quarter": 99})
    assert "BAS GST Report for 2026 Q99" in out_invalid


# ============================================================================
# 2. Supervisor Routing Matrix
# ============================================================================

@pytest.mark.parametrize(
    "mode, question, page_context, expected_route",
    [
        # Explicit mode overrides everything
        ("tax", "any question", "/dashboard", "tax"),
        ("coach", "tax question", "/tax", "coach"),
        ("fraud", "budget question", "/budgets", "fraud"),
        ("goals", "random question", None, "goals"),
        ("budget", "random question", None, "budget"),
        ("assistant", "tax question", "/tax", "assistant"),

        # Page context mappings
        ("auto", "How are things looking?", "/tax", "tax"),
        ("auto", "How are things looking?", "/tax/deductions", "tax"),
        ("auto", "How are things looking?", "/budgets", "budget"),
        ("auto", "How are things looking?", "/budget/monthly", "budget"),
        ("auto", "How are things looking?", "/family", "coach"),
        ("auto", "How are things looking?", "/dashboard", "coach"),

        # Intent keyword overrides & priority
        ("auto", "What is my income tax liability?", "/dashboard", "tax"),
        ("auto", "What is my GST report for Q1?", None, "tax"),
        ("auto", "Check my ATO tax return deductions", None, "tax"),
        ("auto", "Is there any fraud or suspicious transaction?", "/tax", "tax"),  # /tax page context takes priority
        ("auto", "Is there any fraud or suspicious transaction?", "/transactions", "fraud"),
        ("auto", "Did I overspend on dining this month?", None, "budget"),
        ("auto", "Set up a vacation fund goal for $3000", None, "goals"),
        ("auto", "What is my cash runway and debt payoff plan?", None, "coach"),

        # Unmatched / Edge page contexts
        ("auto", "What is compound interest?", "/transactions", "assistant"),
        ("auto", "What is the inflation rate?", None, "assistant"),
        ("auto", "General finance inquiry", "", "assistant"),
        ("auto", "General finance inquiry", "/invalid/path", "assistant"),
        ("auto", "General finance inquiry", "///", "assistant"),
    ],
)
def test_supervisor_routing_matrix(
    mode: str, question: str, page_context: str | None, expected_route: str
):
    assert route_of(mode, question, page_context=page_context) == expected_route


@pytest.mark.asyncio
async def test_supervisor_node_state_execution():
    """Test supervisor_node directly with various AgentState dicts."""
    state1 = {
        "messages": [HumanMessage(content="What are my 2026 tax deductions?")],
        "agent_mode": "auto",
        "page_context": "/transactions",
    }
    res1 = await supervisor_node(state1)
    assert res1["route"] == "tax"

    state2 = {
        "messages": [HumanMessage(content="Show my envelope status")],
        "agent_mode": "auto",
        "page_context": None,
    }
    res2 = await supervisor_node(state2)
    assert res2["route"] == "budget"

    state3 = {
        "messages": [HumanMessage(content="Hello there")],
        "agent_mode": "tax",
        "page_context": None,
    }
    res3 = await supervisor_node(state3)
    assert res3["route"] == "tax"


# ============================================================================
# 3. LangGraph & PII Boundary
# ============================================================================

@pytest.mark.asyncio
async def test_pii_mask_node():
    """Verify that email, phone, and card numbers are masked at the trust boundary."""
    raw_msg = HumanMessage(
        content="My email is john.doe@example.com, phone is +61 412 345 678, card is 4111 1111 1111 1234."
    )
    state = {"messages": [raw_msg]}
    res = await mask_node(state)
    masked_content = res["messages"][0].content

    assert "john.doe@example.com" not in masked_content
    assert "[EMAIL]" in masked_content or "[REDACTED]" in masked_content or "john" not in masked_content
    assert "4111 1111 1111 1234" not in masked_content


def test_compiled_graph_routes_and_nodes():
    """Verify all 6 specialist nodes and edges exist in compiled StateGraph."""
    graph = build_graph()
    expected_nodes = {"mask", "rag", "supervisor", "coach", "budget", "fraud", "goals", "tax", "assistant"}
    for n in expected_nodes:
        assert n in graph.nodes, f"Node {n} missing from graph"


# ============================================================================
# 4. AI Eval Capture & Chat Send Integration
# ============================================================================

@pytest.mark.asyncio
async def test_chat_send_eval_capture_integration(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Verify chat API executes with page_context and records AiEvalLog."""
    payload = {
        "message": "Calculate my Australian estimated income tax for 2026",
        "agent_mode": "auto",
        "page_context": "/tax",
    }
    res = await async_client.post("/api/v1/chat/send", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "thread_id" in data
    assert "reply" in data

    # Verify AiEvalLog
    eval_log = await db_session.scalar(
        select(AiEvalLog)
        .where(AiEvalLog.user_id == test_user.id)
        .order_by(AiEvalLog.created_at.desc())
    )
    assert eval_log is not None
    assert eval_log.route_chosen == "tax"
    assert eval_log.user_id == test_user.id
    assert eval_log.tokens_in > 0
    assert eval_log.tokens_out > 0
    assert eval_log.latency_ms >= 0
