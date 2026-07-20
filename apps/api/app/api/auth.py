from fastapi import APIRouter, Request, Response

from app.api.deps import SESSION_COOKIE, CurrentUser, DbSession
from app.api.schemas import LoginRequest, MessageEnvelope, RegisterRequest, UserEnvelope, UserOut
from app.core.config import Environment, get_settings
from app.db.models import User
from app.services import auth as auth_service
from app.services.auth import SESSION_TTL

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.environment is Environment.PRODUCTION,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")


@router.post("/register", response_model=UserEnvelope, status_code=201)
async def register(payload: RegisterRequest, response: Response, db: DbSession) -> UserEnvelope:
    user, token = await auth_service.register_user(
        db, email=payload.email, password=payload.password, full_name=payload.full_name
    )
    set_session_cookie(response, token)
    return UserEnvelope(data=_user_out(user))


@router.post("/login", response_model=UserEnvelope)
async def login(payload: LoginRequest, response: Response, db: DbSession) -> UserEnvelope:
    user, token = await auth_service.login(db, email=payload.email, password=payload.password)
    set_session_cookie(response, token)
    return UserEnvelope(data=_user_out(user))


@router.post("/logout", response_model=MessageEnvelope)
async def logout(request: Request, response: Response, db: DbSession) -> MessageEnvelope:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await auth_service.logout(db, token=token)
    clear_session_cookie(response)
    return MessageEnvelope(data={"status": "keluar"})


@router.get("/me", response_model=UserEnvelope)
async def me(user: CurrentUser) -> UserEnvelope:
    return UserEnvelope(data=_user_out(user))
