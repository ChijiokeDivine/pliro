"""DCA models - Create recurring_payments and dca_execution_logs tables

Revision ID: dca_v1
Revises: b26076fea5cd
Create Date: 2026-05-14 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dca_v1'
down_revision = 'b26076fea5cd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create recurring_payments table
    op.create_table(
        'recurring_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(50), nullable=False),
        sa.Column('recipient_address', sa.String(100), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('token_symbol', sa.String(20), nullable=False, server_default='USDC'),
        sa.Column('chain', sa.String(50), nullable=False, server_default='ethereum'),
        sa.Column('recurrence_type', sa.String(20), nullable=False),
        sa.Column('cron_expression', sa.String(50), nullable=False),
        sa.Column('next_execution_at', sa.DateTime(), nullable=True),
        sa.Column('last_execution_at', sa.DateTime(), nullable=True),
        sa.Column('execution_count', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_recurring_payments_user_id', 'user_id'),
        sa.Index('ix_recurring_payments_next_execution_at', 'next_execution_at'),
        sa.Index('ix_recurring_payments_status', 'status'),
        sa.Index('ix_recurring_payments_created_at', 'created_at'),
    )
    
    # Create dca_execution_logs table
    op.create_table(
        'dca_execution_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recurring_payment_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(50), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=False),
        sa.Column('executed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('transaction_hash', sa.String(100), nullable=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('token_symbol', sa.String(20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('block_number', sa.Integer(), nullable=True),
        sa.Column('gas_used', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['recurring_payment_id'], ['recurring_payments.id'], ),
        sa.Index('ix_dca_execution_logs_recurring_payment_id', 'recurring_payment_id'),
        sa.Index('ix_dca_execution_logs_user_id', 'user_id'),
        sa.Index('ix_dca_execution_logs_created_at', 'created_at'),
        sa.UniqueConstraint('transaction_hash', name='uq_dca_execution_logs_tx_hash'),
    )


def downgrade() -> None:
    op.drop_table('dca_execution_logs')
    op.drop_table('recurring_payments')
