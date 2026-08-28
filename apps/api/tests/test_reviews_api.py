import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.api.review_schemas import CreateReviewRequest
from app.main import create_app
from tests.conftest import fresh_connection


def test_review_request_validation() -> None:
    req = CreateReviewRequest(rating=5, comment="Hasil foto sangat memuaskan!")
    assert req.rating == 5
    assert req.comment == "Hasil foto sangat memuaskan!"

    with pytest.raises(ValidationError):
        CreateReviewRequest(rating=6)

    with pytest.raises(ValidationError):
        CreateReviewRequest(rating=0)


def test_reviews_route_registration() -> None:
    app = create_app()
    paths = app.openapi()["paths"]
    assert "/api/v1/bookings/{booking_id}/reviews" in paths
    assert "/api/v1/bookings/{booking_id}/review" in paths
    assert "/api/v1/creators/{creator_id}/reviews" in paths


@pytest.mark.integration
async def test_review_lifecycle_and_creator_rating_calculation() -> None:
    async with fresh_connection() as connection:
        client_id = uuid.uuid4()
        creator_user_id = uuid.uuid4()
        creator_profile_id = uuid.uuid4()
        booking_id = uuid.uuid4()
        session_id = uuid.uuid4()
        token_hash = "test_review_token_hash_1"

        # Insert client and creator users
        await connection.execute(
            text(
                """
                INSERT INTO users (id, email, password_hash, full_name, is_admin)
                VALUES
                    (:c_id, 'client_rev@jepret.local', 'hash', 'Klien Review', false),
                    (:cr_id, 'creator_rev@jepret.local', 'hash', 'Kreator Review', false)
                """
            ),
            {"c_id": client_id, "cr_id": creator_user_id},
        )
        await connection.execute(
            text(
                """
                INSERT INTO creator_profiles (
                    id, user_id, display_name, city, bio, specialty,
                    starting_price_idr, status, rating_average, review_count
                )
                VALUES (
                    :id, :user_id, 'Studio Review', 'Bandung', 'Bio', 'photography',
                    500000, 'approved', 0.0, 0
                )
                """
            ),
            {"id": creator_profile_id, "user_id": creator_user_id},
        )
        await connection.execute(
            text(
                """
                INSERT INTO sessions (id, user_id, token_hash, expires_at)
                VALUES (:id, :user_id, :token_hash, now() + interval '1 day')
                """
            ),
            {"id": session_id, "user_id": client_id, "token_hash": token_hash},
        )
        await connection.execute(
            text(
                """
                INSERT INTO bookings (
                    id, client_id, creator_profile_id, event_date,
                    event_city, notes, status, quoted_price_idr
                )
                VALUES (
                    :id, :client_id, :creator_profile_id, '2026-09-01',
                    'Bandung', '', 'completed', 500000
                )
                """
            ),
            {
                "id": booking_id,
                "client_id": client_id,
                "creator_profile_id": creator_profile_id,
            },
        )
