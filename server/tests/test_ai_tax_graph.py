"""Unit and integration tests for AI Tax Tools, LangGraph Tax Agent, and Eval Capture."""
from __future__ import annotations

from datetime import date
import uuid

import pytest
from httpx import AsyncClient
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graph import ROUTES, build_graph, route_of, run_chat
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


@pytest.mark.asyncio
async def test_tax_tools_presence():
    """Verify that all tax tools are declared and available."""
    assert len(ALL_TAX_TOOLS) == 3
    tool_names = [t.name for t in ALL_TAX_TOOLS]
    assert "tax_summary" in tool_names
    assert "deduction_overview" in tool_names
    assert "gst_report" in tool_names


@pytest.mark.asyncio
async def test_tax_summary_tool_execution(db_session: AsyncSession, test_user: User, test_account: Account):
    """Test tax_summary tool computes gross income, deductions, taxable income, and Medicare levy."""
    set_agent_context(db_session, test_user.id)

    # Add income transaction
    income_txn = Transaction(
        account_id=test_account.id,
        user_id=test_user.id,
        amount_minor=10000000,  # $100,000 AUD
        currency="AUD",
        description="Salary and consulting income",
        merchant_raw="Client",
        date=date(2026, 3, 15),
        is_income=True,
    )
    db_session.add(income_txn)

    # Add tax category and deduction
    cat = TaxCategory(name="Tools & Hardware", code="D4_TOOLS", type=TaxCategoryType.DEDUCTION)
    db_session.add(cat)
    await db_session.flush()

    ded = TaxDeduction(
        user_id=test_user.id,
        tax_category_id=cat.id,
        amount_minor=1000000,  # $10,000 AUD
        gst_claimed_minor=90909,
        tax_year=2026,
        notes="Laptop and peripherals",
    )
    db_session.add(ded)
    await db_session.commit()

    output = await tax_summary.ainvoke({"tax_year": 2026})
    assert "Tax Summary for 2026" in output
    assert "$100000.00" in output
    assert "$10000.00" in output
    assert "$90000.00" in output
    assert "Medicare Levy" in output


@pytest.mark.asyncio
async def test_deduction_overview_tool_execution(db_session: AsyncSession, test_user: User):
    """Test deduction_overview tool returns itemized category breakdowns."""
    set_agent_context(db_session, test_user.id)

    cat = TaxCategory(name="Home Office", code="D2_HOME_OFFICE", type=TaxCategoryType.DEDUCTION)
    db_session.add(cat)
    await db_session.flush()

    ded = TaxDeduction(
        user_id=test_user.id,
        tax_category_id=cat.id,
        amount_minor=250000,  # $2,500 AUD
        gst_claimed_minor=22727,
        tax_year=2026,
        notes="Office desk and ergonomic chair",
    )
    db_session.add(ded)
    await db_session.commit()

    output = await deduction_overview.ainvoke({"tax_year": 2026})
    assert "Tax Deductions for 2026" in output
    assert "Home Office" in output
    assert "$2500.00" in output


@pytest.mark.asyncio
async def test_gst_report_tool_execution(db_session: AsyncSession, test_user: User, test_account: Account):
    """Test gst_report tool returns BAS figures (G1, 1A, 1B, Net GST)."""
    set_agent_context(db_session, test_user.id)

    # Q1 sale
    sale_txn = Transaction(
        account_id=test_account.id,
        user_id=test_user.id,
        amount_minor=5500000,  # $55,000 AUD
        currency="AUD",
        description="Q1 Service Revenue",
        merchant_raw="Client",
        date=date(2026, 2, 10),
        is_income=True,
    )
    db_session.add(sale_txn)

    cat = TaxCategory(name="Equipment", code="D4_EQUIPMENT", type=TaxCategoryType.DEDUCTION)
    db_session.add(cat)
    await db_session.flush()

    ded = TaxDeduction(
        user_id=test_user.id,
        tax_category_id=cat.id,
        amount_minor=1100000,
        gst_claimed_minor=100000,  # $1,000 GST paid
        tax_year=2026,
    )
    db_session.add(ded)
    await db_session.commit()

    output = await gst_report.ainvoke({"tax_year": 2026, "quarter": 1})
    assert "BAS GST Report for 2026 Q1" in output
    assert "G1 (Total Sales): $55000.00" in output
    assert "1A (GST on Sales): $5000.00" in output
    assert "1B (GST on Purchases / Credits): $1000.00" in output
    assert "Net GST Payable: $4000.00" in output


def test_routing_decisions_with_page_context():
    """Verify route_of assigns the expected agent based on page_context and intent."""
    assert "tax" in ROUTES
    assert route_of("auto", "How much tax do I owe?", page_context="/tax") == "tax"
    assert route_of("auto", "What is my GST?", page_context="/dashboard") == "tax"
    assert route_of("auto", "Show me my budget breakdown", page_context="/budgets") == "budget"
    assert route_of("auto", "What did we spend this month?", page_context="/family") == "coach"
    assert route_of("auto", "What is my cash runway?", page_context=None) == "coach"
    assert route_of("auto", "Is there any duplicate charge?", page_context=None) == "fraud"
    assert route_of("auto", "Create a vacation goal for $5000", page_context=None) == "goals"
    assert route_of("auto", "Explain compound interest", page_context=None) == "assistant"


@pytest.mark.asyncio
async def test_graph_builder_includes_tax_node():
    """Verify LangGraph compiles with the tax specialist node."""
    graph = build_graph()
    assert graph is not None
    assert "tax" in graph.nodes


@pytest.mark.asyncio
async def test_chat_api_with_page_context_and_eval_logging(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
):
    """Verify chat API executes with page_context and logs an AiEvalLog entry with route_chosen='tax'."""
    payload = {
        "message": "What is my tax summary for 2026?",
        "agent_mode": "auto",
        "page_context": "/tax",
    }
    res = await async_client.post("/api/v1/chat/send", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "thread_id" in data
    assert "reply" in data

    # Verify AiEvalLog record exists in DB
    eval_log = await db_session.scalar(
        select(AiEvalLog)
        .where(AiEvalLog.user_id == test_user.id)
        .order_by(AiEvalLog.created_at.desc())
    )
    assert eval_log is not None
    assert eval_log.route_chosen == "tax"
    assert eval_log.tokens_in > 0
    assert eval_log.tokens_out > 0
    assert eval_log.latency_ms >= 0
