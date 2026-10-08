"""users.google_sub -> oauth_sub ("<provider>:<id>"), so more than one OAuth provider can sign users in

Revision ID: a1c0de5e0002
Revises: a1c0de5e0001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c0de5e0002"
down_revision: Union[str, Sequence[str], None] = "a1c0de5e0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "google_sub", new_column_name="oauth_sub", type_=sa.String(80))
    op.execute("UPDATE users SET oauth_sub = 'google:' || oauth_sub WHERE oauth_sub NOT LIKE '%:%'")


def downgrade() -> None:
    op.execute("UPDATE users SET oauth_sub = substr(oauth_sub, 8) WHERE oauth_sub LIKE 'google:%'")
    op.alter_column("users", "oauth_sub", new_column_name="google_sub", type_=sa.String(64))
