"""FinanceBuddy AI engine — LangGraph supervisor with specialist sub-agents.

    START → mask PII → supervisor (LLM or heuristic router)
          ├─ coach        : cash-flow & debt coaching   (forecast/budget/debt tools)
          ├─ budget       : budgets & overspend analysis
          ├─ fraud        : anomalies, duplicates, alerts
          ├─ goals        : savings strategies
          └─ assistant    : general finance Q&A grounded via pgvector RAG
        → END

Deep-agent behaviour: specialists are ReAct agents over scoped tool subsets;
the supervisor routes on intent; every boundary is PII-masked; provider
failover happens inside FallbackChatModel.
"""
from __future__ import annotations

import uuid
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

from app import jev
from app.ai import rag
from app.ai.llm_router import complete_json, get_chat_model
from app.ai.pii import mask_pii
from app.ai.tools import (
    budget_status,
    propose_budget,
    propose_goal,
    propose_recategorize,
    debt_overview,
    deduction_overview,
    forecast_cashflow,
    goal_overview,
    gst_report,
    list_accounts,
    recent_alerts,
    search_transactions,
    spending_summary,
    subscriptions_detected,
    tax_summary,
)
from app.core.logging import get_logger

log = get_logger("ai_graph")

SYSTEM_BASE = (
    "You are FinanceBuddy, a professional personal-finance coach inside a "
    "privacy-first app. Rules:\n"
    "1. Never give licensed investment or tax advice; educate and suggest.\n"
    "2. Use tools for any user-specific numbers — never invent figures.\n"
    "3. Be concise, concrete, and actionable. Use short bullet lists.\n"
    "4. Currency amounts come from tools; keep the user's currency.\n"
    "5. You cannot change the user's data. To suggest a change use a propose_* tool, then tell the "
    "user to review and confirm the card. Never say a change has been made.\n"
)

COACH_PROMPT = SYSTEM_BASE + (
    "You are the Cash-Flow Coach: diagnose cash flow, forecast runway, "
    "recommend envelope adjustments and debt payoff order."
)
BUDGET_PROMPT = SYSTEM_BASE + "You are the Budget Analyst: analyze envelopes, find overspending, propose allocations."
FRAUD_PROMPT = SYSTEM_BASE + "You are the Fraud Sentinel: explain alerts, duplicate charges, unusual patterns calmly and precisely."
GOALS_PROMPT = SYSTEM_BASE + "You are the Goals Advisor: design savings plans, auto-adjust contributions, track progress."
TAX_PROMPT = SYSTEM_BASE + (
    "You are the Tax Specialist: calculate Australian estimated taxes, analyze deductions, "
    "prepare quarterly BAS (GST 1A vs 1B), and identify deductible business expenses."
)
ASSISTANT_PROMPT = SYSTEM_BASE + "You are a knowledgeable financial-literacy assistant. Ground answers in the provided reference material."

ROUTES = ("coach", "budget", "fraud", "goals", "tax", "assistant")


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    thread_id: str
    agent_mode: str
    page_context: str | None
    page_summary: dict | None
    route: str
    rag_context: str


MAX_PAGE_SUMMARY_CHARS = 2000


def page_summary_prompt(summary: dict | None) -> str:
    """Compact, PII-masked rendering of what the user is looking at, for the system prompt."""
    if not summary:
        return ""
    import json

    text = mask_pii(json.dumps(summary, ensure_ascii=False, default=str))[:MAX_PAGE_SUMMARY_CHARS]
    return f"\n\nWhat the user is looking at in the app right now (JSON):\n{text}"


# ── Nodes ───────────────────────────────────────────────────────────────

async def mask_node(state: AgentState) -> dict:
    """PII-mask all human messages at the trust boundary."""
    masked = []
    for m in state["messages"]:
        if isinstance(m.content, str):
            m = m.model_copy(update={"content": mask_pii(m.content)})
        masked.append(m)
    return {"messages": masked}


async def rag_node(state: AgentState) -> dict:
    """Retrieve grounding docs for assistant-style queries."""
    db = state.get("_db")
    query = next((m.content for m in reversed(state["messages"])
                  if isinstance(m, HumanMessage)), "")
    if not db or not query:
        return {}
    try:
        context, _titles = await rag.build_context(db, query, uuid.UUID(state["user_id"]))
        return {"rag_context": context}
    except Exception as exc:
        log.warning("rag_failed", error=str(exc))
        return {}


async def supervisor_node(state: AgentState) -> dict:
    """Route by requested mode, page_context, or LLM classification with keyword fallback."""
    explicit = state.get("agent_mode") or "auto"
    if explicit in ROUTES:
        return {"route": explicit}

    page_context = (state.get("page_context") or "").lower()
    question = next((m.content for m in reversed(state["messages"]) if isinstance(m.content, str)), "")
    qlow = question.lower()

    tax_keywords = [
        "tax", "taxes", "taxation", "bas", "gst", "deduction", "deductible",
        "ato", "abn", "medicare", "income tax", "bracket", "tax return",
        "tax liability", "tax refund",
    ]

    # Prioritize tax agent when page_context contains /tax or query relates to tax/BAS/GST/deductions
    if "/tax" in page_context or any(w in qlow for w in tax_keywords):
        return {"route": "tax"}

    # Prioritize budget agent when page_context contains /budgets
    if "/budgets" in page_context or "/budget" in page_context:
        return {"route": "budget"}

    # Prioritize coach agent on family or dashboard context
    if "/family" in page_context or "/dashboard" in page_context:
        return {"route": "coach"}

    keywords = {
        "fraud": ["fraud", "suspicious", "duplicate", "unusual", "stolen", "scam", "chargeback"],
        "budget": ["budget", "envelope", "overspend", "allocation", "afford"],
        "goals": ["goal", "save", "saving", "target", "vacation fund"],
        "coach": ["cash flow", "forecast", "runway", "debt", "payoff", "coach", "advice", "plan"],
    }
    for route, words in keywords.items():
        if any(w in qlow for w in words):
            return {"route": route}

    try:
        data = await complete_json(
            f'Route this finance question to one of {list(ROUTES)}.\n'
            f'Page context: "{page_context}"\n'
            f'Question: "{question[:500]}"\n'
            'Reply JSON: {"route": "<name>"}',
            system="You are an intent router.",
        )
        route = (data or {}).get("route")
        if route in ROUTES:
            return {"route": route}
    except Exception as exc:
        log.warning("supervisor_llm_failed", error=str(exc))
    return {"route": "assistant"}


def _make_specialist(name: str, prompt: str, tools: list, model=None):
    async def _node(state: AgentState, config: RunnableConfig) -> dict:
        llm = model or get_chat_model()
        system_content = prompt + page_summary_prompt(state.get("page_summary"))
        if state.get("rag_context"):
            system_content += f"\n\nReference material:\n{state['rag_context']}"
        db = state.get("_db")
        if db is not None and state.get("user_id"):
            from app.ai.tools import agent_context, set_agent_context
            try:
                # Keep the caller's collector so proposals/blocks reach the chat service.
                set_agent_context(db, uuid.UUID(state["user_id"]), agent_context().get("collector"))
            except Exception:
                pass
        agent = create_react_agent(llm, tools, prompt=system_content)
        result = await agent.ainvoke({"messages": state["messages"]}, config=config)
        final = result["messages"][-1]
        provider = None
        try:
            meta = result.get("llm_output") or {}
            provider = meta.get("provider")
        except Exception:
            pass
        content = final.content if isinstance(final.content, str) else "".join(map(str, final.content))
        ai_msg = AIMessage(content=content)
        resp_meta = {"route": name}
        if provider:
            resp_meta["provider"] = provider
        ai_msg.response_metadata = resp_meta
        return {"messages": [ai_msg]}
    _node.__name__ = f"{name}_node"
    return _node


def _select_route(state: AgentState) -> str:
    route = state.get("route")
    return route if route in ROUTES else "assistant"


def build_graph(db_session=None):
    """Build (and cache per-process) the compiled supervisor graph."""
    global _compiled
    if _compiled is not None:
        return _compiled

    g = StateGraph(AgentState)
    g.add_node("mask", mask_node)
    g.add_node("rag", rag_node)
    g.add_node("supervisor", supervisor_node)

    g.add_node("coach", _make_specialist("coach", COACH_PROMPT,
                                         [list_accounts, spending_summary, forecast_cashflow,
                                          budget_status, debt_overview, subscriptions_detected]))
    g.add_node("budget", _make_specialist("budget", BUDGET_PROMPT,
                                          [budget_status, spending_summary, search_transactions,
                                           propose_budget, propose_recategorize]))
    g.add_node("fraud", _make_specialist("fraud", FRAUD_PROMPT,
                                         [recent_alerts, search_transactions, subscriptions_detected,
                                          propose_recategorize]))
    g.add_node("goals", _make_specialist("goals", GOALS_PROMPT,
                                         [goal_overview, list_accounts, forecast_cashflow, propose_goal]))
    g.add_node("tax", _make_specialist("tax", TAX_PROMPT,
                                       [tax_summary, deduction_overview, gst_report,
                                        search_transactions, spending_summary]))
    g.add_node("assistant", _make_specialist("assistant", ASSISTANT_PROMPT,
                                             [list_accounts, spending_summary, search_transactions]))

    g.add_edge(START, "mask")
    g.add_edge("mask", "rag")
    g.add_edge("rag", "supervisor")
    g.add_conditional_edges(
        "supervisor",
        _select_route,
        {r: r for r in ROUTES},
    )
    for route in ROUTES:
        g.add_edge(route, END)

    # bind db session into state via partial — set through config instead
    _compiled = g.compile()
    return _compiled


_compiled = None


def _initial_state(messages, user_id, thread_id, agent_mode, page_context, page_summary,
                   db_session, collector) -> dict:
    state = {
        "messages": messages, "user_id": user_id, "thread_id": thread_id,
        "agent_mode": agent_mode, "page_context": page_context, "page_summary": page_summary,
        "rag_context": "",
    }
    if db_session is not None:
        state["_db"] = db_session  # consumed by rag_node
        from app.ai.tools import set_agent_context
        try:
            set_agent_context(db_session, uuid.UUID(user_id), collector)
        except Exception:
            pass
    return state


async def run_chat(messages: list[BaseMessage], user_id: str, thread_id: str,
                   agent_mode: str = "auto", page_context: str | None = None,
                   db_session=None, page_summary: dict | None = None,
                   collector: dict | None = None) -> AIMessage:
    if (handled := await jev.try_handle(messages, user_id, db_session, collector)) is not None:
        return handled
    graph = build_graph()
    state = _initial_state(messages, user_id, thread_id, agent_mode, page_context, page_summary,
                           db_session, collector)
    result = await graph.ainvoke(state, config={"configurable": {"thread_id": thread_id}})
    return result["messages"][-1]


async def stream_chat(messages: list[BaseMessage], user_id: str, thread_id: str,
                      agent_mode: str = "auto", page_context: str | None = None,
                      db_session=None, page_summary: dict | None = None,
                      collector: dict | None = None):
    """Same graph as run_chat, but yields {"type": "delta"|"tool"|"final", ...} as it runs.

    Only tokens produced inside a specialist node are forwarded (the router's JSON and RAG are not).
    The final event carries the authoritative message; clients replace their streamed buffer with it.
    """
    if (handled := await jev.try_handle(messages, user_id, db_session, collector)) is not None:
        yield {"type": "delta", "text": handled.content}
        yield {"type": "final", "message": handled}
        return
    graph = build_graph()
    state = _initial_state(messages, user_id, thread_id, agent_mode, page_context, page_summary,
                           db_session, collector)
    root_run_id = None
    final: AIMessage | None = None
    async for ev in graph.astream_events(state, config={"configurable": {"thread_id": thread_id}},
                                         version="v2"):
        if root_run_id is None:
            root_run_id = ev.get("run_id")
        kind = ev.get("event")
        ns = str((ev.get("metadata") or {}).get("langgraph_checkpoint_ns", "")).split(":")[0]
        if kind == "on_chat_model_stream" and ns in ROUTES:
            chunk = ev["data"].get("chunk")
            text = chunk.content if chunk is not None and isinstance(chunk.content, str) else ""
            if text:
                yield {"type": "delta", "text": text}
        elif kind == "on_tool_start" and ns in ROUTES:
            yield {"type": "tool", "name": ev.get("name", "")}
        elif kind == "on_chain_end" and ev.get("run_id") == root_run_id:
            output = ev["data"].get("output") or {}
            msgs = output.get("messages") if isinstance(output, dict) else None
            if msgs:
                final = msgs[-1]
    if final is None:
        raise RuntimeError("graph produced no final message")
    yield {"type": "final", "message": final}


def route_of(mode: str, question: str, page_context: str | None = None) -> str:
    """Expose routing decision for tests/evals without running the graph."""
    if mode in ROUTES:
        return mode

    page_ctx = (page_context or "").lower()
    qlow = question.lower()

    tax_words = [
        "tax", "taxes", "taxation", "bas", "gst", "deduction", "deductible",
        "ato", "abn", "medicare", "income tax", "bracket", "tax return",
        "tax liability", "tax refund",
    ]
    if "/tax" in page_ctx or any(w in qlow for w in tax_words):
        return "tax"
    if "/budgets" in page_ctx or "/budget" in page_ctx:
        return "budget"
    if "/family" in page_ctx or "/dashboard" in page_ctx:
        return "coach"

    keywords = {
        "fraud": ["fraud", "suspicious", "duplicate", "unusual", "stolen", "scam", "chargeback"],
        "budget": ["budget", "envelope", "overspend", "allocation", "afford"],
        "goals": ["goal", "save", "saving", "target", "vacation fund"],
        "coach": ["cash flow", "forecast", "runway", "debt", "payoff", "coach", "advice", "plan"],
    }
    for route, words in keywords.items():
        if any(w in qlow for w in words):
            return route
    return "assistant"
