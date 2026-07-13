from fastapi import FastAPI

from app.api.system import router as system_router
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Jepret API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)
    app.include_router(system_router)
    return app


app = create_app()
