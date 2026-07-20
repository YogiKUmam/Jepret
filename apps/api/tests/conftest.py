import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from app.db.session import get_engine


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@jepret.local"


@pytest.fixture
async def email_cleanup() -> AsyncIterator[list[str]]:
    """Collects emails created during a test and removes their users afterwards."""
    emails: list[str] = []
    yield emails
    if emails:
        async with get_engine().begin() as connection:
            await connection.execute(
                text("DELETE FROM users WHERE email = ANY(:emails)"), {"emails": emails}
            )
