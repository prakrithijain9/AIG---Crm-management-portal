"""create admin users table

Revision ID: 5b4a0b13a9f1
Revises: 09d6732c3643
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b4a0b13a9f1'
down_revision: Union[str, Sequence[str], None] = '09d6732c3643'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Only the admin_users table and its index; the CRM tables are not touched.
    op.create_table('admin_users',
    sa.Column('username', sa.String(length=150), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('token_version', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("btrim(username) <> ''", name=op.f('ck_admin_users_username_not_blank')),
    sa.CheckConstraint("username = btrim(username)", name=op.f('ck_admin_users_username_trimmed')),
    sa.CheckConstraint("username ~ '^[A-Za-z0-9._@-]+$'", name=op.f('ck_admin_users_username_valid_characters')),
    sa.CheckConstraint("password_hash <> ''", name=op.f('ck_admin_users_password_hash_not_blank')),
    sa.CheckConstraint(r"password_hash ~ '^\$[a-z0-9-]{1,32}(\$[A-Za-z0-9+/=.,-]+){2,}$'", name=op.f('ck_admin_users_password_hash_phc_format')),
    sa.CheckConstraint('token_version >= 0', name=op.f('ck_admin_users_token_version_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_users'))
    )
    op.create_index('uq_admin_users_username_lower', 'admin_users', [sa.literal_column('lower(username)')], unique=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # Removes only what upgrade() created.
    op.drop_index('uq_admin_users_username_lower', table_name='admin_users')
    op.drop_table('admin_users')
    # ### end Alembic commands ###
