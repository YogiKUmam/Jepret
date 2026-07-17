import uuid

import pytest
from sqlalchemy import text

from app.db.session import get_engine


@pytest.mark.integration
async def test_users_table_accepts_insert_and_unique_email() -> None:
    email = f"schema-{uuid.uuid4().hex}@jepret.local"
    async with get_engine().begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name)"
                " VALUES (:id, :email, 'x', 'Schema Test')"
            ),
            {"id": str(uuid.uuid4()), "email": email},
        )
        found = await connection.scalar(
            text("SELECT count(*) FROM users WHERE email = :email"), {"email": email}
        )
        await connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
    assert found == 1
