"""Event pipeline consumer.

Subscribes to the Redis Stream (or local fallback queue) and reacts to
domain events: anomaly analysis on new transactions, overspend checks,
WebSocket fan-out of alerts. Run standalone or in-process via lifespan.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import uuid

from app.core.logging import get_logger
from app.db.session import SessionFactory
from app.services.events import bus, ws_manager
from app.services.anomaly import analyze_transaction, scan_subscription_duplicates, overspend_check
from app.models import Budget

log = get_logger("worker")


async def handle_event(event: dict) -> None:
    etype = event.get("type", "")
    payload = {}
    try:
        payload = json.loads(event.get("payload", "{}"))
    except json.JSONDecodeError:
        pass
    user_id = event.get("user_id") or None

    if etype == "transaction.created" and user_id and payload.get("transaction_id"):
        async with SessionFactory() as db:
            from sqlalchemy import select

            from app.models import Transaction

            txn = await db.scalar(select(Transaction).where(
                Transaction.id == uuid.UUID(payload["transaction_id"])))
            if txn:
                alerts = await analyze_transaction(db, txn)
                log.info("anomaly_scan_done", transaction=payload["transaction_id"],
                         alerts=len(alerts))
                # budget overspend check against active budgets
                budgets = (await db.execute(
                    select(Budget).where(Budget.user_id == txn.user_id,
                                         Budget.active.is_(True)))).scalars().all()
                for b in budgets:
                    with contextlib.suppress(Exception):
                        await overspend_check(db, b.id)

    elif etype == "alert.created" and user_id:
        await bus.notify_user(user_id, {"kind": "alert", "payload": payload})
        await ws_manager.send_to_user(user_id, {"kind": "alert", **payload})

    elif etype == "transaction.labeled" and user_id:
        log.info("feedback_recorded", merchant_norm=payload.get("merchant_norm"))


async def run_forever(poll_interval: float = 1.0) -> None:
    await bus.connect()
    log.info("event_consumer_started")
    idle_cycles = 0
    while True:
        batch = await bus.read_batch(count=10, block_ms=int(max(poll_interval * 1000, 500)))
        if not batch:
            idle_cycles += 1
            continue
        for entry_id, event in batch:
            try:
                await handle_event(event)
            except Exception as exc:
                log.error("event_handler_failed", type=event.get("type"), error=str(exc))
            await bus.ack(entry_id)


if __name__ == "__main__":
    asyncio.run(run_forever())
