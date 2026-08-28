"""Add reviews, disputes, and creator ratings schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260828_0007"
down_revision = "20260816_0006"
branch_labels = None
depends_on = None

ACTIVE_STATUS_SQL = (
    "status IN ('accepted', 'awaiting_payment', 'confirmed', "
    "'in_progress', 'delivered', 'disputed')"
)
BOOKING_STATUS_SQL = (
    "status IN ('requested', 'accepted', 'awaiting_payment', 'confirmed', "
    "'in_progress', 'delivered', 'rejected', 'completed', 'cancelled', 'disputed')"
)
PHASE6_ACTIVE_STATUS_SQL = (
    "status IN ('accepted', 'awaiting_payment', 'confirmed', 'in_progress', 'delivered')"
)
PHASE6_BOOKING_STATUS_SQL = (
    "status IN ('requested', 'accepted', 'awaiting_payment', 'confirmed', "
    "'in_progress', 'delivered', 'rejected', 'completed', 'cancelled')"
)


def upgrade() -> None:
    op.drop_index("uq_bookings_active_date", table_name="bookings")
    op.drop_constraint("ck_booking_status_valid", "bookings", type_="check")
    op.create_check_constraint("ck_booking_status_valid", "bookings", BOOKING_STATUS_SQL)
    op.create_index(
        "uq_bookings_active_date",
        "bookings",
        ["creator_profile_id", "event_date"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_STATUS_SQL),
    )

    op.add_column(
        "creator_profiles",
        sa.Column("rating_average", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "creator_profiles",
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "creator_profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("creator_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
        sa.UniqueConstraint("booking_id", name="uq_review_booking"),
    )
    op.create_index("ix_reviews_creator_created", "reviews", ["creator_profile_id", "created_at"])
    op.create_index("ix_reviews_client", "reviews", ["client_user_id"])

    op.create_table(
        "disputes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opened_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("reason_category", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column(
            "resolved_by_admin_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "reason_category IN ('not_delivered', 'quality_issue', 'unresponsive', 'other')",
            name="ck_dispute_reason_category_valid",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'under_review', 'resolved_client', 'resolved_creator', 'closed')",
            name="ck_dispute_status_valid",
        ),
        sa.UniqueConstraint("booking_id", name="uq_dispute_booking"),
    )
    op.create_index("ix_disputes_status_created", "disputes", ["status", "created_at"])
    op.create_index("ix_disputes_opened_by", "disputes", ["opened_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_disputes_opened_by", table_name="disputes")
    op.drop_index("ix_disputes_status_created", table_name="disputes")
    op.drop_table("disputes")

    op.drop_index("ix_reviews_client", table_name="reviews")
    op.drop_index("ix_reviews_creator_created", table_name="reviews")
    op.drop_table("reviews")

    op.drop_column("creator_profiles", "review_count")
    op.drop_column("creator_profiles", "rating_average")

    op.drop_index("uq_bookings_active_date", table_name="bookings")
    op.drop_constraint("ck_booking_status_valid", "bookings", type_="check")
    op.create_check_constraint("ck_booking_status_valid", "bookings", PHASE6_BOOKING_STATUS_SQL)
    op.create_index(
        "uq_bookings_active_date",
        "bookings",
        ["creator_profile_id", "event_date"],
        unique=True,
        postgresql_where=sa.text(PHASE6_ACTIVE_STATUS_SQL),
    )
