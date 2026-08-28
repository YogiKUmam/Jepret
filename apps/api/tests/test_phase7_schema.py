import pytest
from sqlalchemy import text

from app.db.models import (
    BOOKING_STATUSES,
    DISPUTE_REASONS,
    DISPUTE_STATUSES,
    Booking,
    CreatorProfile,
    Dispute,
    Review,
)
from tests.conftest import fresh_connection


def test_phase7_model_declarations() -> None:
    assert "disputed" in BOOKING_STATUSES
    assert "not_delivered" in DISPUTE_REASONS
    assert "quality_issue" in DISPUTE_REASONS
    assert "open" in DISPUTE_STATUSES
    assert "resolved_client" in DISPUTE_STATUSES
    assert "resolved_creator" in DISPUTE_STATUSES

    assert Review.__tablename__ == "reviews"
    assert Dispute.__tablename__ == "disputes"

    # Verify review columns and constraints
    assert hasattr(Review, "rating")
    assert hasattr(Review, "comment")
    assert hasattr(Review, "booking_id")
    assert hasattr(Review, "client_user_id")
    assert hasattr(Review, "creator_profile_id")

    # Verify dispute columns
    assert hasattr(Dispute, "booking_id")
    assert hasattr(Dispute, "opened_by_user_id")
    assert hasattr(Dispute, "reason_category")
    assert hasattr(Dispute, "description")
    assert hasattr(Dispute, "status")
    assert hasattr(Dispute, "resolution_notes")
    assert hasattr(Dispute, "resolved_by_admin_user_id")

    # Verify CreatorProfile rating fields
    assert hasattr(CreatorProfile, "rating_average")
    assert hasattr(CreatorProfile, "review_count")

    # Verify relationships
    assert hasattr(Booking, "review")
    assert hasattr(Booking, "dispute")
    assert hasattr(CreatorProfile, "reviews")


@pytest.mark.integration
async def test_phase7_schema_integration() -> None:
    async with fresh_connection() as connection:
        tables = set(
            (
                await connection.scalars(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            ).all()
        )
        assert "reviews" in tables
        assert "disputes" in tables
