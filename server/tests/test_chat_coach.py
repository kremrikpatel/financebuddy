"""AI Coach: proposal-only tools, confirm/cancel actions, thread metadata, streaming."""
from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.graph import stream_chat
from app.ai.tools import new_collector, propose_goal, set_agent_context
from app.core.security import create_access_token, hash_password
from app.models import ChatMessage, ChatThread, Goal, User

API = "/api/v1/chat"


async def _goal_count(db, user_id) -> int:
    return await db.scalar(select(func.count()).select_from(Goal).where(Goal.user_id == user_id))


async def _thread_with_action(db, user, tab="goals") -> tuple[ChatThread, ChatMessage, str]:
    thread = ChatThread(user_id=user.id, title="Save for a trip", agent_mode="auto",
                        source_tab=tab, context={"path": f"/{tab}", "summary": {"goals": 1}})
    db.add(thread)
    await db.flush()
    action_id = uuid.uuid4().hex[:12]
    msg = ChatMessage(thread_id=thread.id, role="assistant", content="Here is a plan.", tool_calls={
        "blocks": [],
        "actions": [{"id": action_id, "type": "create_goal", "status": "pending",
                     "summary": {"name": "Trip"},
                     "payload": {"name": "Trip", "target_minor": 250000, "currency": "USD",
                                 "monthly_amount_minor": 20000, "target_date": None,
                                 "strategy": "fixed_monthly"}}],
    })
    db.add(msg)
    await db.commit()
    return thread, msg, action_id


async def test_propose_goal_never_writes(db_session, test_user):
    collector = new_collector()
    set_agent_context(db_session, test_user.id, collector)
    before = await _goal_count(db_session, test_user.id)

    out = await propose_goal.ainvoke({"name": "Emergency fund", "target_amount": 5000,
                                      "currency": "usd", "monthly_amount": 250})

    assert "Nothing has changed" in out
    assert await _goal_count(db_session, test_user.id) == before
    [action] = collector["actions"]
    assert action["type"] == "create_goal" and action["status"] == "pending"
    assert action["payload"]["target_minor"] == 500000 and action["payload"]["currency"] == "USD"


async def test_confirm_applies_once_then_conflicts(async_client, db_session, test_user, auth_headers):
    _thread, msg, action_id = await _thread_with_action(db_session, test_user)
    before = await _goal_count(db_session, test_user.id)

    pending = (await async_client.get(f"{API}/actions", headers=auth_headers)).json()
    assert any(a["id"] == action_id and a["source_tab"] == "goals" for a in pending)

    res = await async_client.post(f"{API}/actions/{msg.id}/{action_id}", json={"decision": "confirm"},
                                  headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "confirmed"
    assert await _goal_count(db_session, test_user.id) == before + 1

    again = await async_client.post(f"{API}/actions/{msg.id}/{action_id}", json={"decision": "confirm"},
                                    headers=auth_headers)
    assert again.status_code == 409
    assert await _goal_count(db_session, test_user.id) == before + 1
    pending = (await async_client.get(f"{API}/actions", headers=auth_headers)).json()
    assert all(a["id"] != action_id for a in pending)


async def test_cancel_applies_nothing(async_client, db_session, test_user, auth_headers):
    _thread, msg, action_id = await _thread_with_action(db_session, test_user)
    before = await _goal_count(db_session, test_user.id)

    res = await async_client.post(f"{API}/actions/{msg.id}/{action_id}", json={"decision": "cancel"},
                                  headers=auth_headers)

    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert await _goal_count(db_session, test_user.id) == before


async def test_other_user_cannot_decide_action(async_client, db_session, test_user):
    _thread, msg, action_id = await _thread_with_action(db_session, test_user)
    intruder = User(email=f"intruder-{uuid.uuid4().hex[:6]}@example.com",
                    password_hash=hash_password("Intruder123!"), locale="en", base_currency="USD",
                    is_active=True)
    db_session.add(intruder)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(intruder.id)}"}

    res = await async_client.post(f"{API}/actions/{msg.id}/{action_id}", json={"decision": "confirm"},
                                  headers=headers)

    assert res.status_code == 404


async def test_thread_metadata_rename_pin_and_filters(async_client, db_session, test_user, auth_headers):
    thread, _msg, _aid = await _thread_with_action(db_session, test_user, tab="budgets")

    res = await async_client.patch(f"{API}/threads/{thread.id}", json={"title": "Groceries plan", "pinned": True},
                                   headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["title"] == "Groceries plan" and res.json()["pinned"] is True

    listed = (await async_client.get(f"{API}/threads", params={"source_tab": "budgets"}, headers=auth_headers)).json()
    row = next(t for t in listed if t["id"] == str(thread.id))
    assert row["source_tab"] == "budgets" and row["pending_actions"] == 1 and row["context"]["path"] == "/budgets"
    assert listed[0]["pinned"] is True  # pinned threads sort first

    searched = (await async_client.get(f"{API}/threads", params={"q": "groceries"}, headers=auth_headers)).json()
    assert any(t["id"] == str(thread.id) for t in searched)
    other_tab = (await async_client.get(f"{API}/threads", params={"source_tab": "tax"}, headers=auth_headers)).json()
    assert all(t["id"] != str(thread.id) for t in other_tab)


async def test_send_records_origin_tab_and_rejects_oversized_summary(async_client, auth_headers):
    res = await async_client.post(f"{API}/send", headers=auth_headers, json={
        "message": "Where am I overspending this month?", "page_context": "/budgets",
        "page_summary": {"month": "2026-09", "overspent": [{"name": "Dining", "pct": 132}]},
    })
    assert res.status_code == 200, res.text
    thread_id = res.json()["thread_id"]
    assert res.json()["reply"]["id"]
    threads = (await async_client.get(f"{API}/threads", headers=auth_headers)).json()
    assert next(t for t in threads if t["id"] == thread_id)["source_tab"] == "budgets"

    too_big = await async_client.post(f"{API}/send", headers=auth_headers, json={
        "message": "hi", "page_context": "/budgets", "page_summary": {"blob": "x" * 5000}})
    assert too_big.status_code == 422


async def test_stream_chat_yields_deltas_then_final(db_session, test_user):
    events = [ev async for ev in stream_chat([HumanMessage(content="How is my budget looking?")],
                                             str(test_user.id), str(uuid.uuid4()), "budget",
                                             page_context="/budgets", db_session=db_session,
                                             collector=new_collector())]

    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    final = events[-1]
    assert final["type"] == "final"
    assert deltas.strip() and deltas.strip() == final["message"].content.strip()


async def test_ws_stream_turn_persists_reply(monkeypatch, test_engine, db_session, test_user):
    from app.api import ws

    monkeypatch.setattr(ws, "SessionFactory", async_sessionmaker(test_engine, expire_on_commit=False))
    frames: list[dict] = []

    async def send(frame: dict) -> None:
        frames.append(frame)

    await ws._stream_turn(send, str(test_user.id), "req-1",
                          {"message": "Find duplicate or unusual charges", "page_context": "/transactions"})

    kinds = [f["type"] for f in frames]
    assert kinds[0] == "chat.started" and kinds[-1] == "chat.done", kinds
    assert "chat.delta" in kinds
    done = frames[-1]
    saved = await db_session.scalar(select(ChatMessage).where(ChatMessage.id == uuid.UUID(done["reply"]["id"])))
    assert saved is not None and saved.role == "assistant"
