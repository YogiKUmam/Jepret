import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@jepret.local"


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
