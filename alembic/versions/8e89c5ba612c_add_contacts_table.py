"""add contacts table

Revision ID: 8e89c5ba612c
Revises: dca_v1
Create Date: 2026-05-23 18:42:15.970357

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8e89c5ba612c'
down_revision: Union[str, Sequence[str], None] = 'dca_v1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('contacts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('normalized_name', sa.String(length=120), nullable=False),
    sa.Column('chain', sa.String(length=32), nullable=False),
    sa.Column('wallet_address', sa.String(length=128), nullable=False),
    sa.Column('normalized_wallet_address', sa.String(length=128), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['telegram_users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'chain', 'normalized_wallet_address', name='uq_contacts_user_chain_normalized_wallet_address'),
    sa.UniqueConstraint('user_id', 'normalized_name', name='uq_contacts_user_normalized_name')
    )
    op.create_index(op.f('ix_contacts_user_id'), 'contacts', ['user_id'], unique=False)
    op.create_index('ix_contacts_user_normalized_name', 'contacts', ['user_id', 'normalized_name'], unique=False)
    op.create_index('ix_contacts_user_normalized_wallet_address', 'contacts', ['user_id', 'normalized_wallet_address'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_contacts_user_normalized_wallet_address', table_name='contacts')
    op.drop_index('ix_contacts_user_normalized_name', table_name='contacts')
    op.drop_index(op.f('ix_contacts_user_id'), table_name='contacts')
    op.drop_table('contacts')
