"""Create payment_ledger table

Revision ID: 20260131_000002
Revises: 20260131_000001
Create Date: 2026-01-31

Immutable blockchain-like ledger for confirmed payments.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260131_000002"
down_revision: Union[str, None] = "20260131_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("transaction_hash", sa.String(64), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name="fk_payment_ledger_invoice_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("invoice_id", name="uq_payment_ledger_invoice_id"),
        sa.UniqueConstraint("transaction_hash", name="uq_payment_ledger_transaction_hash"),
    )
    op.create_index("ix_payment_ledger_invoice_id", "payment_ledger", ["invoice_id"])
    op.create_index("ix_payment_ledger_transaction_hash", "payment_ledger", ["transaction_hash"])
    op.create_index("ix_payment_ledger_previous_hash", "payment_ledger", ["previous_hash"])


def downgrade() -> None:
    op.drop_index("ix_payment_ledger_previous_hash", table_name="payment_ledger")
    op.drop_index("ix_payment_ledger_transaction_hash", table_name="payment_ledger")
    op.drop_index("ix_payment_ledger_invoice_id", table_name="payment_ledger")
    op.drop_table("payment_ledger")
