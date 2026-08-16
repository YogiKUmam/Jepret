"""Add chat, upload intent, and deliverable schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260816_0006"
down_revision = "20260731_0005"
branch_labels = None
depends_on = None

ACTIVE_STATUS_SQL = (
    "status IN ('accepted', 'awaiting_payment', 'confirmed', 'in_progress', 'delivered')"
)
BOOKING_STATUS_SQL = (
    "status IN ('requested', 'accepted', 'awaiting_payment', 'confirmed', "
    "'in_progress', 'delivered', 'rejected', 'completed', 'cancelled')"
)
PHASE5_ACTIVE_STATUS_SQL = "status IN ('accepted', 'awaiting_payment', 'confirmed')"
PHASE5_BOOKING_STATUS_SQL = (
    "status IN ('requested', 'accepted', 'awaiting_payment', 'confirmed', "
    "'rejected', 'completed', 'cancelled')"
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
    op.add_column("bookings", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("booking_id", name="uq_conversation_booking"),
    )

    op.create_table(
        "upload_intents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False, unique=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "purpose IN ('chat_attachment', 'deliverable')",
            name="ck_upload_purpose_valid",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'expired', 'rejected')",
            name="ck_upload_status_valid",
        ),
    )
    op.create_index("ix_upload_intents_expiry", "upload_intents", ["status", "expires_at"])

    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sender_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("message_type", sa.String(20), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "upload_id",
            UUID(as_uuid=True),
            sa.ForeignKey("upload_intents.id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("attachment_filename", sa.String(255), nullable=True),
        sa.Column("attachment_content_type", sa.String(100), nullable=True),
        sa.Column("attachment_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "conversation_id",
            "sender_user_id",
            "client_message_id",
            name="uq_message_client_id",
        ),
        sa.CheckConstraint(
            "message_type IN ('text', 'attachment', 'system')",
            name="ck_message_type_valid",
        ),
    )
    op.create_index(
        "ix_messages_conversation_created_id",
        "messages",
        ["conversation_id", "created_at", "id"],
    )

    op.create_table(
        "deliverables",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column(
            "upload_id",
            UUID(as_uuid=True),
            sa.ForeignKey("upload_intents.id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(50), nullable=True),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "replaces_deliverable_id",
            UUID(as_uuid=True),
            sa.ForeignKey("deliverables.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(source_type = 'private_file' AND upload_id IS NOT NULL AND external_url IS NULL) "
            "OR (source_type = 'external_link' AND upload_id IS NULL AND external_url IS NOT NULL)",
            name="ck_deliverable_source_valid",
        ),
    )
    op.create_index("ix_deliverables_booking_created", "deliverables", ["booking_id", "created_at"])


def downgrade() -> None:
    op.execute("DELETE FROM deliverables")
    op.execute("DELETE FROM messages")
    op.execute("DELETE FROM upload_intents")
    op.execute("DELETE FROM conversations")
    op.drop_table("deliverables")
    op.drop_table("messages")
    op.drop_table("upload_intents")
    op.drop_table("conversations")

    op.drop_index("uq_bookings_active_date", table_name="bookings")
    op.drop_constraint("ck_booking_status_valid", "bookings", type_="check")
    op.execute(
        "UPDATE bookings SET status = 'confirmed' WHERE status IN ('in_progress', 'delivered')"
    )
    op.create_check_constraint("ck_booking_status_valid", "bookings", PHASE5_BOOKING_STATUS_SQL)
    op.create_index(
        "uq_bookings_active_date",
        "bookings",
        ["creator_profile_id", "event_date"],
        unique=True,
        postgresql_where=sa.text(PHASE5_ACTIVE_STATUS_SQL),
    )
    op.drop_column("bookings", "delivered_at")
    op.drop_column("bookings", "started_at")
