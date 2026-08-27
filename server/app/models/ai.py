"""AI/RAG models: chat threads, messages, knowledge documents."""
from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base, TimestampMixin, UUIDMixin, utcnow


class ChatThread(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_threads"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="New conversation")
    agent_mode: Mapped[str] = mapped_column(String(40), default="auto")  # auto|coach|fraud|budget|goals
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class ChatMessage(UUIDMixin, Base):
    __tablename__ = "chat_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user|assistant|tool|system
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[dict | None] = mapped_column(JSON)
    tokens_in: Mapped[int | None]
    tokens_out: Mapped[int | None]
    provider: Mapped[str | None] = mapped_column(String(50))
    latency_ms: Mapped[int | None]
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class KnowledgeDoc(UUIDMixin, TimestampMixin, Base):
    """RAG corpus — financial literacy content + user-uploaded docs."""

    __tablename__ = "knowledge_docs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)  # NULL => global corpus
    title: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(30), default="guide")  # guide|statement|faq|policy
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(Vector(settings.embedding_dim))
    meta: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (Index("ix_kdoc_embedding", "embedding", postgresql_using="hnsw",
                            postgresql_ops={"embedding": "vector_cosine_ops"}),)
