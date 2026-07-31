"""Add payment tables and payment-aware booking states."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260731_0005"
down_revision = "20260721_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_bookings_accepted_date", table_name="bookings")
    op.drop_constraint("ck_booking_status_valid", "bookings", type_="check")
    op.create_check_constraint(
        "ck_booking_status_valid",
        "bookings",
        (
            "status IN ('requested', 'accepted', 'awaiting_payment', 'confirmed', "
            "'rejected', 'completed', 'cancelled')"
        ),
    )
    op.create_index(
        "uq_bookings_active_date",
        "bookings",
        ["creator_profile_id", "event_date"],
        unique=True,
        postgresql_where=sa.text("status IN ('accepted', 'awaiting_payment', 'confirmed')"),
    )

    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_reference", sa.String(100), nullable=True, unique=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("platform_fee", sa.BigInteger(), nullable=False),
        sa.Column("creator_net", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_metadata", JSONB(), nullable=True),
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
            "status IN ('pending', 'paid', 'held', 'released', 'refunded', 'failed', 'expired')",
            name="ck_payment_status_valid",
        ),
        sa.CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        sa.CheckConstraint("platform_fee >= 0", name="ck_payment_platform_fee_non_negative"),
        sa.CheckConstraint("creator_net >= 0", name="ck_payment_creator_net_non_negative"),
        sa.CheckConstraint(
            "amount = platform_fee + creator_net",
            name="ck_payment_amount_parts_match",
        ),
    )

    op.create_table(
        "payment_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "payment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_event_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_payment_event_provider_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("payment_events")
    op.drop_table("payments")
    op.drop_index("uq_bookings_active_date", table_name="bookings")
    op.drop_constraint("ck_booking_status_valid", "bookings", type_="check")
    op.execute(
        """
        UPDATE bookings
        SET status = 'accepted'
        WHERE status IN ('awaiting_payment', 'confirmed')
        """
    )
    op.create_check_constraint(
        "ck_booking_status_valid",
        "bookings",
        "status IN ('requested', 'accepted', 'rejected', 'completed', 'cancelled')",
    )
    op.create_index(
        "uq_bookings_accepted_date",
        "bookings",
        ["creator_profile_id", "event_date"],
        unique=True,
        postgresql_where=sa.text("status = 'accepted'"),
    )
