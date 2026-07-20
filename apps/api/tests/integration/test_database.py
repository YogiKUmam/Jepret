import pytest
from sqlalchemy import text

from tests.conftest import fresh_connection


@pytest.mark.integration
async def test_postgres_connection_executes_select_one() -> None:
    async with fresh_connection() as connection:
        result = await connection.scalar(text("SELECT 1"))
    assert result == 1
