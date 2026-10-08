"""users.whatsapp (verified number) and wider alert_deliveries.status for "<email>+wa_<status>"

Revision ID: a1c0de5e0003
Revises: a1c0de5e0002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c0de5e0003"
down_revision: Union[str, Sequence[str], None] = "a1c0de5e0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("whatsapp", sa.String(15), nullable=True))
    op.alter_column("alert_deliveries", "status", type_=sa.String(24))


def downgrade() -> None:
    op.alter_column("alert_deliveries", "status", type_=sa.String(12))
    op.drop_column("users", "whatsapp")
