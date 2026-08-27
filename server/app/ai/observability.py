"""Observability: LangSmith / Langfuse / Phoenix / Opik wiring.

All providers activate purely from env config; missing keys are no-ops.
Callbacks returned here are attached to the LLM router and agent runs.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("observability")


def build_callbacks() -> list:
    callbacks: list = []

    # LangSmith — langchain picks this up natively via env vars; nothing to add.

    if settings.langfuse_public_key and settings.langfuse_secret_key:
        try:
            from langfuse.langchain import CallbackHandler as LangfuseHandler

            import os
            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
            os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
            os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
            callbacks.append(LangfuseHandler())
            log.info("langfuse_enabled")
        except ImportError:
            log.info("langfuse_sdk_missing", hint="pip install 'financebuddy-server[obs]'")

    if settings.phoenix_endpoint:
        try:
            import phoenix as px
            from openinference.instrumentation.langchain import LangChainInstrumentor

            tracer = px.Client(endpoint=settings.phoenix_endpoint)
            LangChainInstrumentor().instrument(tracer_provider=tracer)
            log.info("phoenix_enabled", endpoint=settings.phoenix_endpoint)
        except Exception as exc:
            log.info("phoenix_unavailable", error=str(exc))

    return callbacks


def record_feedback(kind: str, **meta) -> None:
    """Hook used by evals (Ragas/Opik/Deepchecks) to emit run feedback."""
    log.info("feedback", kind=kind, **meta)
