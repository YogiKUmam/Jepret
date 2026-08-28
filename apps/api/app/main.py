from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.bookings import router as bookings_router
from app.api.conversations import router as conversations_router
from app.api.creators import router as creators_router
from app.api.deliverables import router as deliverables_router
from app.api.dev_payments import router as dev_payments_router
from app.api.disputes import router as disputes_router
from app.api.payments import router as payments_router
from app.api.profiles import router as profiles_router
from app.api.reviews import router as reviews_router
from app.api.system import router as system_router
from app.api.uploads import router as uploads_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware, OriginCheckMiddleware
from app.core.rate_limit import FixedWindowRateLimiter
from app.db.session import dispose_engine
from app.realtime import ConnectionHub


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings()
    try:
        yield
    finally:
        await app.state.connection_hub.close()
        await dispose_engine()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Jepret API",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(OriginCheckMiddleware)
    install_error_handlers(app)
    app.state.connection_hub = ConnectionHub()
    app.state.message_rate_limiter = FixedWindowRateLimiter(limit=30, window_seconds=60)
    app.state.upload_rate_limiter = FixedWindowRateLimiter(limit=10, window_seconds=60)
    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(profiles_router)
    app.include_router(creators_router)
    app.include_router(bookings_router)
    app.include_router(payments_router)
    app.include_router(dev_payments_router)
    app.include_router(admin_router)
    app.include_router(uploads_router)
    app.include_router(conversations_router)
    app.include_router(deliverables_router)
    app.include_router(reviews_router)
    app.include_router(disputes_router)
    return app


app = create_app()
