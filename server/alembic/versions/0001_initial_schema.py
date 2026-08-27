"""Initial schema for all FinanceBuddy models

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-27 10:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension if on postgres
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 1. users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("locale", sa.String(length=10), server_default="en", nullable=False),
        sa.Column("base_currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("mfa_secret_sealed", sa.Text(), nullable=True),
        sa.Column("recovery_codes", sa.JSON(), nullable=True),
        sa.Column("vault_salt", sa.String(length=64), nullable=True),
        sa.Column("vault_wrapped_dek", sa.Text(), nullable=True),
        sa.Column("vault_verifier", sa.String(length=128), nullable=True),
        sa.Column("vault_algo", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("device", sa.String(length=200), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)

    # 3. passkey_credentials
    op.create_table(
        "passkey_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.String(length=512), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("transports", sa.JSON(), nullable=True),
        sa.Column("device_type", sa.String(length=100), nullable=True),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_passkey_credentials_credential_id", "passkey_credentials", ["credential_id"], unique=True)
    op.create_index("ix_passkey_credentials_user_id", "passkey_credentials", ["user_id"], unique=False)

    # 4. oauth_accounts
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_account_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"], unique=False)
    op.create_index("ix_oauth_provider_account", "oauth_accounts", ["provider", "provider_account_id"], unique=True)

    # 5. audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False)

    # 6. bank_connections
    op.create_table(
        "bank_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("region", sa.String(length=10), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("access_token_sealed", sa.Text(), nullable=True),
        sa.Column("institution_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bank_connections_external_id", "bank_connections", ["external_id"], unique=False)
    op.create_index("ix_bank_connections_user_id", "bank_connections", ["user_id"], unique=False)

    # 7. accounts
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=30), server_default="depository", nullable=False),
        sa.Column("subtype", sa.String(length=40), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("balance_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("is_manual", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["bank_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "external_id", name="uq_account_external"),
    )
    op.create_index("ix_accounts_external_id", "accounts", ["external_id"], unique=False)
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"], unique=False)

    # 8. categories
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=20), server_default="expense", nullable=False),
        sa.Column("color", sa.String(length=9), server_default="#6366f1", nullable=False),
        sa.Column("icon", sa.String(length=50), server_default="wallet", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"], unique=False)
    op.create_index("ix_cat_user_name", "categories", ["user_id", "name"], unique=True)

    # 9. transactions
    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("merchant_raw", sa.Text(), nullable=False),
        sa.Column("merchant_norm", sa.Text(), server_default="", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes_encrypted", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=20), server_default="sync", nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("import_hash", sa.String(length=64), nullable=True),
        sa.Column("pending", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("excluded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_income", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("categorization_method", sa.String(length=20), nullable=True),
        sa.Column("categorization_confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("confirmed_by_user", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("is_split_parent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("receipt_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "external_id", name="uq_txn_external"),
    )
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"], unique=False)
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"], unique=False)
    op.create_index("ix_transactions_confirmed_by_user", "transactions", ["confirmed_by_user"], unique=False)
    op.create_index("ix_transactions_date", "transactions", ["date"], unique=False)
    op.create_index("ix_transactions_import_hash", "transactions", ["import_hash"], unique=False)
    op.create_index("ix_transactions_is_income", "transactions", ["is_income"], unique=False)
    op.create_index("ix_transactions_merchant_norm", "transactions", ["merchant_norm"], unique=False)
    op.create_index("ix_transactions_needs_review", "transactions", ["needs_review"], unique=False)
    op.create_index("ix_transactions_parent_id", "transactions", ["parent_id"], unique=False)
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"], unique=False)
    op.create_index("ix_txn_user_date", "transactions", ["user_id", "date"], unique=False)

    # 10. transaction_splits
    op.create_table(
        "transaction_splits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transaction_splits_transaction_id", "transaction_splits", ["transaction_id"], unique=False)

    # 11. recurring_subscriptions
    op.create_table(
        "recurring_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("merchant_norm", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("avg_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("cadence_days", sa.Integer(), nullable=False),
        sa.Column("first_seen", sa.Date(), nullable=False),
        sa.Column("last_seen", sa.Date(), nullable=False),
        sa.Column("next_expected", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("duplicates_of_id", sa.Uuid(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recurring_subscriptions_duplicates_of_id", "recurring_subscriptions", ["duplicates_of_id"], unique=False)
    op.create_index("ix_recurring_subscriptions_user_id", "recurring_subscriptions", ["user_id"], unique=False)

    # 12. budgets
    op.create_table(
        "budgets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("strategy", sa.String(length=20), server_default="envelope", nullable=False),
        sa.Column("period", sa.String(length=20), server_default="monthly", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("income_planned_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_budgets_user_id", "budgets", ["user_id"], unique=False)

    # 13. budget_envelopes
    op.create_table(
        "budget_envelopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("budget_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("allocated_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rollover", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("carry_in_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_budget_envelopes_budget_id", "budget_envelopes", ["budget_id"], unique=False)
    op.create_index("ix_budget_envelopes_category_id", "budget_envelopes", ["category_id"], unique=False)

    # 14. goals
    op.create_table(
        "goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("target_minor", sa.BigInteger(), nullable=False),
        sa.Column("saved_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("strategy", sa.String(length=30), server_default="fixed_monthly", nullable=False),
        sa.Column("monthly_amount_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("percent_of_income", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goals_user_id", "goals", ["user_id"], unique=False)

    # 15. debts
    op.create_table(
        "debts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("principal_minor", sa.BigInteger(), nullable=False),
        sa.Column("apr_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("min_payment_minor", sa.BigInteger(), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("paid_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_debts_user_id", "debts", ["user_id"], unique=False)

    # 16. alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=10), server_default="info", nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_user_unread", "alerts", ["user_id", "read_at"], unique=False)
    op.create_index("ix_alerts_type", "alerts", ["type"], unique=False)
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"], unique=False)

    # 17. fx_rates
    op.create_table(
        "fx_rates",
        sa.Column("base", sa.String(length=3), nullable=False),
        sa.Column("quote", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("base", "quote"),
    )

    # 18. chat_threads
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), server_default="New conversation", nullable=False),
        sa.Column("agent_mode", sa.String(length=40), server_default="auto", nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_threads_user_id", "chat_threads", ["user_id"], unique=False)

    # 19. chat_messages
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"], unique=False)
    op.create_index("ix_chat_messages_thread_id", "chat_messages", ["thread_id"], unique=False)

    # 20. knowledge_docs
    op.create_table(
        "knowledge_docs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("source_type", sa.String(length=30), server_default="guide", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_docs_user_id", "knowledge_docs", ["user_id"], unique=False)
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_kdoc_embedding",
            "knowledge_docs",
            ["embedding"],
            unique=False,
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index("ix_kdoc_embedding", table_name="knowledge_docs", postgresql_using="hnsw")
    op.drop_index("ix_knowledge_docs_user_id", table_name="knowledge_docs")
    op.drop_table("knowledge_docs")

    op.drop_index("ix_chat_messages_thread_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("ix_chat_threads_user_id", table_name="chat_threads")
    op.drop_table("chat_threads")

    op.drop_table("fx_rates")

    op.drop_index("ix_alerts_user_id", table_name="alerts")
    op.drop_index("ix_alerts_type", table_name="alerts")
    op.drop_index("ix_alert_user_unread", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_debts_user_id", table_name="debts")
    op.drop_table("debts")

    op.drop_index("ix_goals_user_id", table_name="goals")
    op.drop_table("goals")

    op.drop_index("ix_budget_envelopes_category_id", table_name="budget_envelopes")
    op.drop_index("ix_budget_envelopes_budget_id", table_name="budget_envelopes")
    op.drop_table("budget_envelopes")

    op.drop_index("ix_budgets_user_id", table_name="budgets")
    op.drop_table("budgets")

    op.drop_index("ix_recurring_subscriptions_user_id", table_name="recurring_subscriptions")
    op.drop_index("ix_recurring_subscriptions_duplicates_of_id", table_name="recurring_subscriptions")
    op.drop_table("recurring_subscriptions")

    op.drop_index("ix_transaction_splits_transaction_id", table_name="transaction_splits")
    op.drop_table("transaction_splits")

    op.drop_index("ix_txn_user_date", table_name="transactions")
    op.drop_index("ix_transactions_user_id", table_name="transactions")
    op.drop_index("ix_transactions_parent_id", table_name="transactions")
    op.drop_index("ix_transactions_needs_review", table_name="transactions")
    op.drop_index("ix_transactions_merchant_norm", table_name="transactions")
    op.drop_index("ix_transactions_is_income", table_name="transactions")
    op.drop_index("ix_transactions_import_hash", table_name="transactions")
    op.drop_index("ix_transactions_date", table_name="transactions")
    op.drop_index("ix_transactions_confirmed_by_user", table_name="transactions")
    op.drop_index("ix_transactions_category_id", table_name="transactions")
    op.drop_index("ix_transactions_account_id", table_name="transactions")
    op.drop_table("transactions")

    op.drop_index("ix_cat_user_name", table_name="categories")
    op.drop_index("ix_categories_user_id", table_name="categories")
    op.drop_table("categories")

    op.drop_index("ix_accounts_user_id", table_name="accounts")
    op.drop_index("ix_accounts_external_id", table_name="accounts")
    op.drop_table("accounts")

    op.drop_index("ix_bank_connections_user_id", table_name="bank_connections")
    op.drop_index("ix_bank_connections_external_id", table_name="bank_connections")
    op.drop_table("bank_connections")

    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_oauth_provider_account", table_name="oauth_accounts")
    op.drop_index("ix_oauth_accounts_user_id", table_name="oauth_accounts")
    op.drop_table("oauth_accounts")

    op.drop_index("ix_passkey_credentials_user_id", table_name="passkey_credentials")
    op.drop_index("ix_passkey_credentials_credential_id", table_name="passkey_credentials")
    op.drop_table("passkey_credentials")

    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
