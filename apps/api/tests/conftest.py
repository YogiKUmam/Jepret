import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings

VALID_STARTUP_ENVIRONMENT = {
    "JEPRET_ENVIRONMENT": "test",
    "JEPRET_DATABASE_URL": "postgresql+asyncpg://jepret:jepret@db:5432/jepret",
    "JEPRET_PUBLIC_ORIGIN": "http://localhost:8080",
    "JEPRET_MINIO_ENDPOINT": "http://minio:9000",
    "JEPRET_MINIO_PUBLIC_ENDPOINT": "http://localhost:9000",
    "JEPRET_MINIO_ACCESS_KEY": "minioadmin",
    "JEPRET_MINIO_SECRET_KEY": "minioadmin",
}


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@jepret.local"


@pytest.fixture(autouse=True)
def valid_startup_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[None]:
    for name, value in VALID_STARTUP_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    try:
        yield
    finally:
        get_settings.cache_clear()


@asynccontextmanager
async def fresh_connection() -> AsyncIterator[AsyncConnection]:
    """Short-lived engine bound to the current event loop (Windows-safe)."""
    engine = create_async_engine(get_settings().database_url, poolclass=None)
    try:
        async with engine.begin() as connection:
            yield connection
    finally:
        await engine.dispose()


@pytest.fixture
async def email_cleanup() -> AsyncIterator[list[str]]:
    """Collects emails created during a test and removes their users afterwards."""
    emails: list[str] = []
    yield emails
    if emails:
        async with fresh_connection() as connection:
            await connection.execute(
                text("DELETE FROM users WHERE email = ANY(:emails)"), {"emails": emails}
            )


async def make_admin(email: str) -> None:
    async with fresh_connection() as connection:
        await connection.execute(
            text("UPDATE users SET is_admin = true WHERE email = :email"), {"email": email}
        )
