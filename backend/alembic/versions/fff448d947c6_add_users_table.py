"""add users table

Revision ID: fff448d947c6
Revises: 84ab7b3b1146
Create Date: 2026-07-26 21:53:40.628077

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fff448d947c6'
down_revision: Union[str, None] = '84ab7b3b1146'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table('users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('credits_cents', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # Add user_id to api_keys (batch mode for SQLite FK support)
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_api_keys_user_id', ['user_id'], unique=False)
        batch_op.create_foreign_key('fk_api_keys_user_id', 'users', ['user_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.drop_constraint('fk_api_keys_user_id', type_='foreignkey')
        batch_op.drop_index('ix_api_keys_user_id')
        batch_op.drop_column('user_id')

    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
