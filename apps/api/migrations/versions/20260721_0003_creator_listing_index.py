"""Add listing index for the public creator marketplace."""

import sqlalchemy as sa
from alembic import op

revision = "20260721_0003"
down_revision = "20260717_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_creator_profiles_listing",
        "creator_profiles",
        ["status", sa.text("reviewed_at DESC"), sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_creator_profiles_listing", table_name="creator_profiles")
