"""Family profiles, Tax management, and AI Eval models

Revision ID: 0002_family_tax_ai_eval
Revises: 0001_initial_schema
Create Date: 2026-08-28 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_family_tax_ai_eval"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. family_groups
    op.create_table(
        "family_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_family_groups_owner_id", "family_groups", ["owner_id"], unique=False)

    # 2. family_members
    op.create_table(
        "family_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), server_default="member", nullable=False),
        sa.Column("spending_limit_minor", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["family_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family_id", "user_id", name="uq_family_member"),
    )
    op.create_index("ix_family_members_family_id", "family_members", ["family_id"], unique=False)
    op.create_index("ix_family_members_user_id", "family_members", ["user_id"], unique=False)

    # 3. tax_profiles
    op.create_table(
        "tax_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=10), server_default="AU", nullable=False),
        sa.Column("business_type", sa.String(length=30), server_default="sole_trader", nullable=False),
        sa.Column("abn", sa.String(length=20), nullable=True),
        sa.Column("gst_registered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tax_year", name="uq_tax_profile_user_year"),
    )
    op.create_index("ix_tax_profiles_tax_year", "tax_profiles", ["tax_year"], unique=False)
    op.create_index("ix_tax_profiles_user_id", "tax_profiles", ["user_id"], unique=False)
    op.create_index("ix_tax_profile_user_year", "tax_profiles", ["user_id", "tax_year"], unique=False)

    # 4. tax_categories
    op.create_table(
        "tax_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("type", sa.String(length=30), server_default="deduction", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tax_categories_code", "tax_categories", ["code"], unique=True)

    # 5. tax_deductions
    op.create_table(
        "tax_deductions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("tax_category_id", sa.Uuid(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("gst_claimed_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("receipt_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tax_category_id"], ["tax_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tax_deductions_tax_category_id", "tax_deductions", ["tax_category_id"], unique=False)
    op.create_index("ix_tax_deductions_tax_year", "tax_deductions", ["tax_year"], unique=False)
    op.create_index("ix_tax_deductions_transaction_id", "tax_deductions", ["transaction_id"], unique=False)
    op.create_index("ix_tax_deductions_user_id", "tax_deductions", ["user_id"], unique=False)
    op.create_index("ix_tax_deductions_user_year", "tax_deductions", ["user_id", "tax_year"], unique=False)

    # 6. ai_eval_logs
    op.create_table(
        "ai_eval_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("provider_used", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("tokens_in", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("route_chosen", sa.String(length=50), server_default="coach", nullable=False),
        sa.Column("confidence_score", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("pii_fields_masked", sa.Integer(), server_default="0", nullable=False),
        sa.Column("query_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_eval_logs_created_at", "ai_eval_logs", ["created_at"], unique=False)
    op.create_index("ix_ai_eval_logs_message_id", "ai_eval_logs", ["message_id"], unique=False)
    op.create_index("ix_ai_eval_logs_thread_id", "ai_eval_logs", ["thread_id"], unique=False)
    op.create_index("ix_ai_eval_logs_user_id", "ai_eval_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_eval_logs_user_id", table_name="ai_eval_logs")
    op.drop_index("ix_ai_eval_logs_thread_id", table_name="ai_eval_logs")
    op.drop_index("ix_ai_eval_logs_message_id", table_name="ai_eval_logs")
    op.drop_index("ix_ai_eval_logs_created_at", table_name="ai_eval_logs")
    op.drop_table("ai_eval_logs")

    op.drop_index("ix_tax_deductions_user_year", table_name="tax_deductions")
    op.drop_index("ix_tax_deductions_user_id", table_name="tax_deductions")
    op.drop_index("ix_tax_deductions_transaction_id", table_name="tax_deductions")
    op.drop_index("ix_tax_deductions_tax_year", table_name="tax_deductions")
    op.drop_index("ix_tax_deductions_tax_category_id", table_name="tax_deductions")
    op.drop_table("tax_deductions")

    op.drop_index("ix_tax_categories_code", table_name="tax_categories")
    op.drop_table("tax_categories")

    op.drop_index("ix_tax_profile_user_year", table_name="tax_profiles")
    op.drop_index("ix_tax_profiles_tax_year", table_name="tax_profiles")
    op.drop_index("ix_tax_profiles_user_id", table_name="tax_profiles")
    op.drop_table("tax_profiles")

    op.drop_index("ix_family_members_user_id", table_name="family_members")
    op.drop_index("ix_family_members_family_id", table_name="family_members")
    op.drop_table("family_members")

    op.drop_index("ix_family_groups_owner_id", table_name="family_groups")
    op.drop_table("family_groups")