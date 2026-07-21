"""Add bookings table."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260721_0004"
down_revision = "20260721_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "creator_profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("creator_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_city", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("quoted_price_idr", sa.BigInteger(), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'accepted', 'rejected', 'completed', 'cancelled')",
            name="ck_booking_status_valid",
        ),
        sa.CheckConstraint("quoted_price_idr >= 0", name="ck_booking_price_non_negative"),
    )
    op.create_index("ix_bookings_client", "bookings", ["client_id", "created_at"])
    op.create_index("ix_bookings_creator", "bookings", ["creator_profile_id", "created_at"])
    op.create_index(
        "uq_bookings_accepted_date",
        "bookings",
        ["creator_profile_id", "event_date"],
        unique=True,
        postgresql_where=sa.text("status = 'accepted'"),
    )


def downgrade() -> None:
    op.drop_index("uq_bookings_accepted_date", table_name="bookings")
    op.drop_index("ix_bookings_creator", table_name="bookings")
    op.drop_index("ix_bookings_client", table_name="bookings")
    op.drop_table("bookings")
