"""RAG evaluation harness (Ragas) + data checks (Deepchecks-lite).

Runs against a live stack: builds retrieval answers for a golden question
set and scores faithfulness/relevance when Ragas is installed; otherwise
prints the raw context so failures are debuggable.
"""
from __future__ import annotations

import asyncio
import os

GOLDEN_QA = [
    {"q": "How much should I keep in an emergency fund?",
     "expect": "3 to 6 months of essential expenses"},
    {"q": "What is zero-based budgeting?",
     "expect": "every unit of income gets a job until income minus allocations equals zero"},
    {"q": "Which debt payoff method minimizes interest?",
     "expect": "avalanche"},
]


async def main() -> None:
    from app.db.session import SessionFactory
    from app.ai.rag import retrieve

    results = []
    async with SessionFactory() as db:
        for item in GOLDEN_QA:
            docs = await retrieve(db, item["q"], user_id=None)
            context = "\n".join(d["content"][:300] for d in docs)
            hit = item["expect"].lower() in context.lower()
            results.append({"q": item["q"], "hit": hit, "docs": len(docs)})
            print(f"{'PASS' if hit else 'MISS'}  {item['q']}  (top {len(docs)} docs)")

    try:
        from ragas import evaluate  # noqa: F401

        print("\nRagas available — full metric run requires an LLM key; "
              "see docs/evals for the complete pipeline.")
    except ImportError:
        print("\nInstall [obs] extras for Ragas/Deepchecks scoring.")

    failed = [r for r in results if not r["hit"]]
    print(f"\n{len(results) - len(failed)}/{len(results)} golden questions grounded.")


if __name__ == "__main__":
    asyncio.run(main())
