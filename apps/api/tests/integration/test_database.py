import re

import pytest
from sqlalchemy import text

from tests.conftest import fresh_connection


@pytest.mark.integration
async def test_postgres_connection_executes_select_one() -> None:
    async with fresh_connection() as connection:
        result = await connection.scalar(text("SELECT 1"))
    assert result == 1


@pytest.mark.integration
async def test_payment_schema_and_active_booking_states_are_enforced() -> None:
    async with fresh_connection() as connection:
        payment_columns = set(
            (
                await connection.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = 'payments'
                        """
                    )
                )
            ).scalars()
        )
        payment_event_unique = await connection.scalar(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'uq_payment_event_provider_id'
                """
            )
        )
        booking_status_check = await connection.scalar(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'ck_booking_status_valid'
                """
            )
        )
        active_date_index = await connection.scalar(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' AND indexname = 'uq_bookings_active_date'
                """
            )
        )
        old_accepted_date_index = await connection.scalar(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' AND indexname = 'uq_bookings_accepted_date'
                """
            )
        )
        payment_event_lengths = dict(
            (
                await connection.execute(
                    text(
                        """
                        SELECT column_name, character_maximum_length
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'payment_events'
                          AND column_name IN ('provider_event_id', 'event_type')
                        """
                    )
                )
            )
            .tuples()
            .all()
        )
        payment_checks = " ".join(
            (
                await connection.execute(
                    text(
                        """
                        SELECT pg_get_constraintdef(oid)
                        FROM pg_constraint
                        WHERE conrelid = to_regclass('public.payments') AND contype = 'c'
                        ORDER BY conname
                        """
                    )
                )
            ).scalars()
        )

    assert payment_columns == {
        "id",
        "booking_id",
        "provider",
        "provider_reference",
        "idempotency_key",
        "amount_idr",
        "platform_fee_idr",
        "creator_net_idr",
        "status",
        "paid_at",
        "held_at",
        "released_at",
        "refunded_at",
        "raw_metadata",
        "created_at",
        "updated_at",
    }
    assert payment_event_unique == "UNIQUE (provider, provider_event_id)"
    assert payment_event_lengths == {"provider_event_id": 150, "event_type": 50}
    assert booking_status_check is not None
    for status in (
        "requested",
        "accepted",
        "awaiting_payment",
        "confirmed",
        "rejected",
        "completed",
        "cancelled",
    ):
        assert status in booking_status_check
    assert active_date_index is not None
    assert active_date_index.startswith("CREATE UNIQUE INDEX")
    index_predicate = active_date_index.partition(" WHERE ")[2]
    assert "(status)::text = ANY" in index_predicate
    assert set(re.findall(r"'([^']+)'", index_predicate)) == {
        "accepted",
        "awaiting_payment",
        "confirmed",
        "in_progress",
        "delivered",
        "disputed",
    }
    assert old_accepted_date_index is None
    assert "amount_idr > 0" in payment_checks
    assert "platform_fee_idr >= 0" in payment_checks
    assert "creator_net_idr >= 0" in payment_checks
    assert "amount_idr = (platform_fee_idr + creator_net_idr)" in payment_checks
