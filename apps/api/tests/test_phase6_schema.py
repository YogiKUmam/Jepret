import asyncio
import os
import re
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Environment, get_settings
from tests.conftest import fresh_connection


@pytest.mark.integration
async def test_phase6_schema_definitions_are_exact() -> None:
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
        check_definitions = dict(
            (
                await connection.execute(
                    text(
                        """
                        SELECT conname, pg_get_constraintdef(oid, true)
                        FROM pg_constraint
                        WHERE conname IN (
                            'ck_booking_status_valid', 'ck_message_type_valid',
                            'ck_upload_purpose_valid', 'ck_upload_status_valid',
                            'ck_deliverable_source_valid'
                        )
                        """
                    )
                )
            )
            .tuples()
            .all()
        )
        unique_definitions: dict[str, set[str]] = {}
        for table_name in (
            "conversations",
            "messages",
            "upload_intents",
            "deliverables",
        ):
            unique_definitions[table_name] = set(
                (
                    await connection.scalars(
                        text(
                            """
                            SELECT pg_get_constraintdef(oid, true)
                            FROM pg_constraint
                            WHERE conrelid = to_regclass(:table_name) AND contype = 'u'
                            """
                        ),
                        {"table_name": f"public.{table_name}"},
                    )
                ).all()
            )
        upload_nullability = dict(
            (
                await connection.execute(
                    text(
                        """
                        SELECT table_name, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name IN ('messages', 'deliverables')
                          AND column_name = 'upload_id'
                        """
                    )
                )
            )
            .tuples()
            .all()
        )
        foreign_keys = {
            (table_name, constraint_name): (_normalize(definition), delete_action)
            for table_name, constraint_name, definition, delete_action in (
                await connection.execute(
                    text(
                        """
                        SELECT conrelid::regclass::text, conname,
                               pg_get_constraintdef(oid, true), confdeltype::text
                        FROM pg_constraint
                        WHERE contype = 'f'
                          AND conrelid IN (
                              to_regclass('public.conversations'),
                              to_regclass('public.messages'),
                              to_regclass('public.upload_intents'),
                              to_regclass('public.deliverables')
                          )
                        """
                    )
                )
            )
            .tuples()
            .all()
        }
        index_definitions = dict(
            (
                await connection.execute(
                    text(
                        """
                        SELECT indexname,
                               pg_get_indexdef((schemaname || '.' || indexname)::regclass)
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND indexname IN (
                              'uq_bookings_active_date',
                              'ix_messages_conversation_created_id',
                              'ix_upload_intents_expiry',
                              'ix_deliverables_booking_created'
                          )
                        """
                    )
                )
            )
            .tuples()
            .all()
        )

    assert {"conversations", "messages", "upload_intents", "deliverables"} <= tables
    assert _normalize(check_definitions["ck_booking_status_valid"]) == (
        "check (status = any (array['requested', 'accepted', 'awaiting_payment', 'confirmed', "
        "'in_progress', 'delivered', 'rejected', 'completed', 'cancelled', 'disputed']))"
    )
    assert _normalize(check_definitions["ck_message_type_valid"]) == (
        "check (message_type = any (array['text', 'attachment', 'system']))"
    )
    assert _normalize(check_definitions["ck_upload_purpose_valid"]) == (
        "check (purpose = any (array['chat_attachment', 'deliverable']))"
    )
    assert _normalize(check_definitions["ck_upload_status_valid"]) == (
        "check (status = any (array['pending', 'completed', 'expired', 'rejected']))"
    )
    assert _normalize(check_definitions["ck_deliverable_source_valid"]) == (
        "check (source_type = 'private_file' and upload_id is not null and external_url is null "
        "or source_type = 'external_link' and upload_id is null and external_url is not null)"
    )
    assert unique_definitions == {
        "conversations": {"UNIQUE (booking_id)"},
        "messages": {
            "UNIQUE (conversation_id, sender_user_id, client_message_id)",
            "UNIQUE (upload_id)",
        },
        "upload_intents": {"UNIQUE (object_key)"},
        "deliverables": {"UNIQUE (upload_id)"},
    }
    assert upload_nullability == {"messages": "YES", "deliverables": "YES"}
    assert {
        (table_name, definition, delete_action)
        for (table_name, _), (definition, delete_action) in foreign_keys.items()
    } == {
        (
            "conversations",
            "foreign key (booking_id) references bookings(id) on delete cascade",
            "c",
        ),
        (
            "upload_intents",
            "foreign key (booking_id) references bookings(id) on delete cascade",
            "c",
        ),
        ("upload_intents", "foreign key (requested_by_user_id) references users(id)", "a"),
        (
            "messages",
            "foreign key (conversation_id) references conversations(id) on delete cascade",
            "c",
        ),
        ("messages", "foreign key (sender_user_id) references users(id)", "a"),
        ("messages", "foreign key (upload_id) references upload_intents(id)", "a"),
        (
            "deliverables",
            "foreign key (booking_id) references bookings(id) on delete cascade",
            "c",
        ),
        ("deliverables", "foreign key (uploaded_by_user_id) references users(id)", "a"),
        ("deliverables", "foreign key (upload_id) references upload_intents(id)", "a"),
        (
            "deliverables",
            "foreign key (replaces_deliverable_id) references deliverables(id)",
            "a",
        ),
    }

    indexes = {name: _normalize(definition) for name, definition in index_definitions.items()}
    active_index = indexes["uq_bookings_active_date"]
    assert active_index == (
        "create unique index uq_bookings_active_date on public.bookings using btree "
        "(creator_profile_id, event_date) where ((status) = any ((array['accepted', "
        "'awaiting_payment', 'confirmed', 'in_progress', 'delivered', 'disputed'])))"
    )
    assert indexes["ix_messages_conversation_created_id"] == (
        "create index ix_messages_conversation_created_id on public.messages using btree "
        "(conversation_id, created_at, id)"
    )
    assert indexes["ix_upload_intents_expiry"] == (
        "create index ix_upload_intents_expiry on public.upload_intents using btree "
        "(status, expires_at)"
    )
    assert indexes["ix_deliverables_booking_created"] == (
        "create index ix_deliverables_booking_created on public.deliverables using btree "
        "(booking_id, created_at)"
    )


@pytest.mark.integration
@pytest.mark.parametrize("phase6_status", ["in_progress", "delivered"])
async def test_each_phase6_active_status_blocks_the_same_creator_date(
    phase6_status: str,
) -> None:
    client_id = uuid.uuid4()
    creator_user_id = uuid.uuid4()
    creator_profile_id = uuid.uuid4()
    async with fresh_connection() as connection:
        await _insert_owners(connection, client_id, creator_user_id, creator_profile_id)
        await _insert_booking(
            connection,
            uuid.uuid4(),
            client_id,
            creator_profile_id,
            date(2026, 12, 10),
            phase6_status,
        )
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await _insert_booking(
                    connection,
                    uuid.uuid4(),
                    client_id,
                    creator_profile_id,
                    date(2026, 12, 10),
                    "accepted",
                )
        await connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": client_id})
        await connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": creator_user_id})


@pytest.mark.integration
async def test_isolated_database_refuses_non_test_before_engine_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine_creation_attempted = False

    def fail_if_engine_is_created(*args: object, **kwargs: object) -> AsyncEngine:
        nonlocal engine_creation_attempted
        engine_creation_attempted = True
        raise AssertionError("database engine creation must not be reached")

    get_settings.cache_clear()
    monkeypatch.setenv("JEPRET_ENVIRONMENT", "production")
    monkeypatch.setattr(sys.modules[__name__], "create_async_engine", fail_if_engine_is_created)
    try:
        with pytest.raises(RuntimeError, match="requires JEPRET_ENVIRONMENT=test"):
            async with isolated_phase6_database():
                pytest.fail("non-test environment entered disposable database context")
    finally:
        get_settings.cache_clear()

    assert engine_creation_attempted is False


@pytest.mark.integration
async def test_phase6_migration_downgrade_is_destructive_and_reversible() -> None:
    async with isolated_phase6_database() as (database_url, engine):
        await run_alembic(database_url, "upgrade", "20260731_0005")
        client_id = uuid.uuid4()
        creator_user_id = uuid.uuid4()
        creator_profile_id = uuid.uuid4()
        in_progress_id = uuid.uuid4()
        delivered_id = uuid.uuid4()
        async with engine.begin() as connection:
            await _insert_owners(connection, client_id, creator_user_id, creator_profile_id)
            await _insert_booking(
                connection,
                in_progress_id,
                client_id,
                creator_profile_id,
                date(2027, 1, 10),
                "confirmed",
            )
            await _insert_booking(
                connection,
                delivered_id,
                client_id,
                creator_profile_id,
                date(2027, 1, 11),
                "confirmed",
            )

        await run_alembic(database_url, "upgrade", "head")
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE bookings
                    SET status = CASE WHEN id = :first_id THEN 'in_progress' ELSE 'delivered' END,
                        started_at = now(),
                        delivered_at = CASE WHEN id = :second_id THEN now() ELSE NULL END
                    WHERE id IN (:first_id, :second_id)
                    """
                ),
                {"first_id": in_progress_id, "second_id": delivered_id},
            )
            await _insert_phase6_rows(connection, in_progress_id, creator_user_id)

        await run_alembic(database_url, "downgrade", "20260731_0005")
        async with engine.begin() as connection:
            booking_statuses = dict(
                (
                    await connection.execute(
                        text("SELECT id, status FROM bookings WHERE id IN (:first_id, :second_id)"),
                        {"first_id": in_progress_id, "second_id": delivered_id},
                    )
                )
                .tuples()
                .all()
            )
            phase6_tables = set(
                (
                    await connection.scalars(
                        text(
                            """
                            SELECT table_name FROM information_schema.tables
                            WHERE table_schema = 'public'
                              AND table_name IN (
                                  'conversations', 'messages', 'upload_intents', 'deliverables'
                              )
                            """
                        )
                    )
                ).all()
            )
            phase6_columns = set(
                (
                    await connection.scalars(
                        text(
                            """
                            SELECT column_name FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = 'bookings'
                              AND column_name IN ('started_at', 'delivered_at')
                            """
                        )
                    )
                ).all()
            )
            phase5_check = await connection.scalar(
                text(
                    "SELECT pg_get_constraintdef(oid, true) FROM pg_constraint "
                    "WHERE conname = 'ck_booking_status_valid'"
                )
            )
            phase5_index = await connection.scalar(
                text(
                    "SELECT pg_get_indexdef((schemaname || '.' || indexname)::regclass) "
                    "FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = 'uq_bookings_active_date'"
                )
            )
        assert booking_statuses == {
            in_progress_id: "confirmed",
            delivered_id: "confirmed",
        }
        assert phase6_tables == set()
        assert phase6_columns == set()
        assert _normalize(phase5_check) == (
            "check (status = any (array['requested', 'accepted', 'awaiting_payment', "
            "'confirmed', 'rejected', 'completed', 'cancelled']))"
        )
        normalized_phase5_index = _normalize(phase5_index)
        assert normalized_phase5_index == (
            "create unique index uq_bookings_active_date on public.bookings using btree "
            "(creator_profile_id, event_date) where ((status) = any ((array['accepted', "
            "'awaiting_payment', 'confirmed'])))"
        )

        await run_alembic(database_url, "upgrade", "head")
        async with engine.begin() as connection:
            restored_tables = set(
                (
                    await connection.scalars(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public'"
                        )
                    )
                ).all()
            )
            counts = dict(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT 'conversations', count(*) FROM conversations
                            UNION ALL SELECT 'messages', count(*) FROM messages
                            UNION ALL SELECT 'upload_intents', count(*) FROM upload_intents
                            UNION ALL SELECT 'deliverables', count(*) FROM deliverables
                            """
                        )
                    )
                )
                .tuples()
                .all()
            )
        assert {"conversations", "messages", "upload_intents", "deliverables"} <= restored_tables
        assert counts == {
            "conversations": 0,
            "messages": 0,
            "upload_intents": 0,
            "deliverables": 0,
        }


@asynccontextmanager
async def isolated_phase6_database() -> AsyncIterator[tuple[str, AsyncEngine]]:
    settings = get_settings()
    if settings.environment is not Environment.TEST:
        raise RuntimeError("Disposable database test requires JEPRET_ENVIRONMENT=test")
    configured_url = make_url(settings.database_url)
    database_name = f"jepret_phase6_test_{uuid.uuid4().hex[:16]}"
    admin_url = configured_url.set(database="postgres")
    database_url = configured_url.set(database=database_name)
    admin_engine = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    database_engine = create_async_engine(database_url, poolclass=NullPool)
    database_created = False
    try:
        async with admin_engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        database_created = True
        yield database_url.render_as_string(hide_password=False), database_engine
    finally:
        await database_engine.dispose()
        if database_created:
            async with admin_engine.connect() as connection:
                await connection.execute(
                    text(
                        """
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = :database_name AND pid <> pg_backend_pid()
                        """
                    ),
                    {"database_name": database_name},
                )
                await connection.execute(text(f'DROP DATABASE "{database_name}"'))
        await admin_engine.dispose()


async def run_alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["JEPRET_DATABASE_URL"] = database_url
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        *arguments,
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=60)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        pytest.fail(output.decode(errors="replace"))


def _normalize(definition: str) -> str:
    normalized = definition.lower()
    normalized = re.sub(r"::(?:character varying|text)(?:\[\])?", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


async def _insert_owners(
    connection: AsyncConnection,
    client_id: uuid.UUID,
    creator_user_id: uuid.UUID,
    creator_profile_id: uuid.UUID,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO users (id, email, password_hash, full_name)
            VALUES
                (:client_id, :client_email, 'test-hash', 'Schema Client'),
                (:creator_user_id, :creator_email, 'test-hash', 'Schema Creator')
            """
        ),
        {
            "client_id": client_id,
            "client_email": f"phase6-client-{client_id}@jepret.local",
            "creator_user_id": creator_user_id,
            "creator_email": f"phase6-creator-{creator_user_id}@jepret.local",
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO creator_profiles (
                id, user_id, display_name, city, bio, specialty, starting_price_idr, status
            )
            VALUES (
                :id, :user_id, 'Schema Creator', 'Bandung', '', 'wedding', 1000000, 'approved'
            )
            """
        ),
        {"id": creator_profile_id, "user_id": creator_user_id},
    )


async def _insert_booking(
    connection: AsyncConnection,
    booking_id: uuid.UUID,
    client_id: uuid.UUID,
    creator_profile_id: uuid.UUID,
    event_date: date,
    status: str,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO bookings (
                id, client_id, creator_profile_id, event_date, event_city,
                notes, status, quoted_price_idr
            )
            VALUES (
                :id, :client_id, :creator_profile_id, :event_date, 'Bandung',
                '', :status, 1000000
            )
            """
        ),
        {
            "id": booking_id,
            "client_id": client_id,
            "creator_profile_id": creator_profile_id,
            "event_date": event_date,
            "status": status,
        },
    )


async def _insert_phase6_rows(
    connection: AsyncConnection,
    booking_id: uuid.UUID,
    creator_user_id: uuid.UUID,
) -> None:
    conversation_id = uuid.uuid4()
    chat_upload_id = uuid.uuid4()
    deliverable_upload_id = uuid.uuid4()
    await connection.execute(
        text("INSERT INTO conversations (id, booking_id) VALUES (:id, :booking_id)"),
        {"id": conversation_id, "booking_id": booking_id},
    )
    for upload_id, purpose in (
        (chat_upload_id, "chat_attachment"),
        (deliverable_upload_id, "deliverable"),
    ):
        await connection.execute(
            text(
                """
                INSERT INTO upload_intents (
                    id, booking_id, requested_by_user_id, purpose, object_key,
                    filename, content_type, size_bytes, status, expires_at, completed_at
                )
                VALUES (
                    :id, :booking_id, :user_id, :purpose, :object_key,
                    'result.pdf', 'application/pdf', 1024, 'completed',
                    now() + interval '1 hour', now()
                )
                """
            ),
            {
                "id": upload_id,
                "booking_id": booking_id,
                "user_id": creator_user_id,
                "purpose": purpose,
                "object_key": f"phase6-test/{upload_id}",
            },
        )
    await connection.execute(
        text(
            """
            INSERT INTO messages (
                id, conversation_id, sender_user_id, client_message_id, message_type,
                upload_id, attachment_filename, attachment_content_type, attachment_size_bytes
            )
            VALUES (
                :id, :conversation_id, :user_id, :client_message_id, 'attachment',
                :upload_id, 'result.pdf', 'application/pdf', 1024
            )
            """
        ),
        {
            "id": uuid.uuid4(),
            "conversation_id": conversation_id,
            "user_id": creator_user_id,
            "client_message_id": uuid.uuid4(),
            "upload_id": chat_upload_id,
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO deliverables (
                id, booking_id, uploaded_by_user_id, title, source_type, upload_id,
                media_type, filename, content_type, size_bytes
            )
            VALUES (
                :id, :booking_id, :user_id, 'Hasil', 'private_file', :upload_id,
                'document', 'result.pdf', 'application/pdf', 1024
            )
            """
        ),
        {
            "id": uuid.uuid4(),
            "booking_id": booking_id,
            "user_id": creator_user_id,
            "upload_id": deliverable_upload_id,
        },
    )
