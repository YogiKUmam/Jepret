from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models import User
from app.db.session import get_session
from app.services.auth import get_user_by_session_token

SESSION_COOKIE = "jepret_session"

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise DomainError("UNAUTHENTICATED", "Silakan masuk terlebih dahulu.", 401)
    user = await get_user_by_session_token(db, token=token)
    if user is None:
        raise DomainError("UNAUTHENTICATED", "Sesi tidak valid atau kedaluwarsa.", 401)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise DomainError("FORBIDDEN", "Akses khusus admin.", 403)
    return user


AdminUser = Annotated[User, Depends(require_admin)]
