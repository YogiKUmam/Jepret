import pytest
from sqlalchemy import text

from app.db.session import get_engine


@pytest.mark.integration
async def test_postgres_connection_executes_select_one() -> None:
    async with get_engine().connect() as connection:
        result = await connection.scalar(text("SELECT 1"))
    assert result == 1
