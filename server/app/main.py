"""FinanceBuddy API entrypoint."""
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth as auth_router
from app.api import chat as chat_router
from app.api import finance as finance_router
from app.api import integrations as integrations_router
from app.api import planning as planning_router
from app.api import system as system_router
from app.api import ws as ws_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.services.auth_service import AuthError
from app.services.events import bus

configure_logging()
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # observability callbacks (LangSmith via env; Langfuse/Phoenix if configured)
    from app.ai.observability import build_callbacks

    build_callbacks()

    await bus.connect()

    # lightweight in-process event consumer (compose deployment uses the dedicated worker)
    worker_task: asyncio.Task | None = None
    if settings.app_env != "production":
        from app.workers.event_consumer import run_forever

        worker_task = asyncio.create_task(run_forever())

    yield

    if worker_task:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
    await bus.close()


app = FastAPI(
    title="FinanceBuddy API",
    version="0.1.0",
    description="AI personal finance platform — aggregation, coaching, budgeting, fraud detection.",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_prod else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


API = "/api/v1"
app.include_router(auth_router.router, prefix=API)
app.include_router(finance_router.router, prefix=API)
app.include_router(finance_router.router, prefix=f"{API}/finance")
app.include_router(planning_router.router, prefix=API)
app.include_router(planning_router.router, prefix=f"{API}/planning")
app.include_router(planning_router.router, prefix=f"{API}/finance/planning")
app.include_router(planning_router.router, prefix=f"{API}/finance")
app.include_router(integrations_router.router, prefix=API)
app.include_router(chat_router.router, prefix=API)
app.include_router(system_router.router, prefix=API)
app.include_router(ws_router.router)


@app.get("/", tags=["system"])
async def root():
    return {"name": "FinanceBuddy", "docs": "/docs", "api": API}
