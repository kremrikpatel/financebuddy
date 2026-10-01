"""Chat thread metadata for the AI Coach hub (origin tab, context snapshot, pin)

Revision ID: 0003_chat_thread_meta
Revises: 0002_family_tax_ai_eval
Create Date: 2026-09-28 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_chat_thread_meta"
down_revision: str | None = "0002_family_tax_ai_eval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_threads", sa.Column("source_tab", sa.String(length=40), nullable=True))
    op.add_column("chat_threads", sa.Column("context", sa.JSON(), nullable=True))
    op.add_column(
        "chat_threads",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_chat_threads_user_pinned", "chat_threads", ["user_id", "pinned"])


def downgrade() -> None:
    op.drop_index("ix_chat_threads_user_pinned", table_name="chat_threads")
    op.drop_column("chat_threads", "pinned")
    op.drop_column("chat_threads", "context")
    op.drop_column("chat_threads", "source_tab")
