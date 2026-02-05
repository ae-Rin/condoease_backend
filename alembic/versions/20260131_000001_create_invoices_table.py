"""Create invoices table

Revision ID: 20260131_000001
Revises: None
Create Date: 2026-01-31

This migration creates the invoices table for tracking tenant billing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260131_000001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the invoices table."""
    op.create_table(
        'invoices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('lease_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'PAID', 'OVERDUE', name='invoice_status'),
            nullable=False,
            server_default='PENDING'
        ),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['tenant_id'],
            ['tenants.tenant_id'],
            name='fk_invoices_tenant_id',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ["lease_id"],
            ["leases.lease_id"],
            name="fk_invoices_lease_id",
            ondelete="NO ACTION",
        ),
    )
    
    # Create indexes for common queries
    op.create_index('ix_invoices_tenant_id', 'invoices', ['tenant_id'])
    op.create_index('ix_invoices_lease_id', 'invoices', ['lease_id'])
    op.create_index('ix_invoices_due_date', 'invoices', ['due_date'])
    op.create_index('ix_invoices_status', 'invoices', ['status'])


def downgrade() -> None:
    """Drop the invoices table."""
    op.drop_index('ix_invoices_status', table_name='invoices')
    op.drop_index('ix_invoices_due_date', table_name='invoices')
    op.drop_index('ix_invoices_lease_id', table_name='invoices')
    op.drop_index('ix_invoices_tenant_id', table_name='invoices')
    op.drop_table('invoices')
    
    # Drop the enum type
    op.execute("DROP TYPE IF EXISTS invoice_status")
