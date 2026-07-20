from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.db.models import User, UserSession

SESSION_TTL = timedelta(days=30)

# Constant Argon2 hash used to equalise timing when the email is unknown.
_DUMMY_HASH = hash_password("jepret-dummy-password")


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def _create_session(db: AsyncSession, user: User) -> str:
    token = generate_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=datetime.now(UTC) + SESSION_TTL,
        )
    )
    await db.flush()
    return token


async def register_user(
    db: AsyncSession, *, email: str, password: str, full_name: str
) -> tuple[User, str]:
    email = normalize_email(email)
    existing = await db.scalar(select(User.id).where(User.email == email))
    if existing is not None:
        raise DomainError("EMAIL_TAKEN", "Email sudah terdaftar.", 409)

    user = User(email=email, password_hash=hash_password(password), full_name=full_name.strip())
    db.add(user)
    await db.flush()
    token = await _create_session(db, user)
    await db.commit()
    return user, token


async def login(db: AsyncSession, *, email: str, password: str) -> tuple[User, str]:
    user = await db.scalar(select(User).where(User.email == normalize_email(email)))
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok:
        raise DomainError("INVALID_CREDENTIALS", "Email atau password salah.", 401)

    token = await _create_session(db, user)
    await db.commit()
    return user, token


async def logout(db: AsyncSession, *, token: str) -> None:
    await db.execute(
        delete(UserSession).where(UserSession.token_hash == hash_session_token(token))
    )
    await db.commit()


async def get_user_by_session_token(db: AsyncSession, *, token: str) -> User | None:
    result = await db.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == hash_session_token(token),
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    return result
