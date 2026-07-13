# Jepret Phase 0–1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membangun foundation Jepret yang dapat dijalankan lokal melalui satu origin, memiliki shell PWA mobile-first, FastAPI modular monolith, PostgreSQL/MinIO, generated API contract, CI, dan quality gates yang terverifikasi.

**Architecture:** Caddy menjadi same-origin gateway untuk Next.js pada `/`, FastAPI pada `/api/v1/*`, dan WebSocket probe pada `/ws/*`. FastAPI menjadi pemilik kontrak OpenAPI dan persistence; TypeScript client dihasilkan ke workspace contracts. Docker Compose menjalankan service wajib tanpa Redis, sedangkan Redis tersedia sebagai profile opsional.

**Tech Stack:** Node.js 24; Next.js 16.2.10; React 19.2.7; TypeScript 7.0.2; Tailwind CSS 4.3.2; TanStack Query 5.101.2; Vitest 4.1.10; Playwright 1.61.1; Python 3.13; FastAPI 0.139.0; Pydantic 2.13.4; SQLAlchemy 2.0.51; Alembic 1.18.5; PostgreSQL 18; Caddy 2; MinIO; Docker Compose; GitHub Actions.

---

## File Map

### Root and governance

- `AGENTS.md`: aturan kerja repository dari master prompt.
- `.editorconfig`: line ending, indentation, dan encoding lintas platform.
- `.env.example`: seluruh variable lokal tanpa secret.
- `package.json`: npm workspaces dan command lintas platform.
- `package-lock.json`: lock dependency JavaScript.
- `Makefile`: wrapper command yang diminta master prompt.
- `scripts/verify.mjs`: quality runner lintas Windows/Linux.
- `docs/assumptions.md`: asumsi Phase 0.
- `docs/architecture.md`: runtime diagram dan keputusan foundation.
- `docs/implementation-plan.md`: progress tracker fase master prompt.

### Backend

- `apps/api/pyproject.toml`, `apps/api/uv.lock`: dependency dan lock Python.
- `apps/api/app/main.py`: application factory.
- `apps/api/app/core/config.py`: validated settings.
- `apps/api/app/core/errors.py`: stable API error envelope.
- `apps/api/app/core/logging.py`: structured logging configuration.
- `apps/api/app/core/middleware.py`: correlation ID propagation.
- `apps/api/app/db/session.py`: async engine/session lifecycle.
- `apps/api/app/api/system.py`: health, readiness, dan WebSocket development probe.
- `apps/api/scripts/export_openapi.py`: deterministic OpenAPI export.
- `apps/api/alembic.ini`, `apps/api/migrations/*`: migration environment dan empty baseline revision.
- `apps/api/tests/*`: unit dan integration tests.

### Contracts

- `packages/contracts/package.json`: contract generation scripts.
- `packages/contracts/openapi.json`: exported backend schema.
- `packages/contracts/src/schema.d.ts`: generated TypeScript schema.
- `packages/contracts/src/index.ts`: public contract entry point.

### Frontend

- `apps/web/package.json`: pinned web dependencies.
- `apps/web/src/app/*`: root layout, homepage, error, loading, dan global tokens.
- `apps/web/src/components/layout/*`: header dan bottom navigation.
- `apps/web/src/components/creators/creator-preview-card.tsx`: realistic non-interactive preview.
- `apps/web/src/lib/query-provider.tsx`: TanStack Query boundary.
- `apps/web/src/test/*`: Vitest setup dan component tests.
- `apps/web/e2e/foundation.spec.ts`: mobile shell and gateway smoke tests.

### Runtime and CI

- `apps/web/Dockerfile`, `apps/api/Dockerfile`: reproducible service images.
- `infra/gateway/Caddyfile`: same-origin routing.
- `docker-compose.yml`: required services and optional Redis profile.
- `.github/workflows/ci.yml`: quality pipeline.

## Version Baseline

Versi package berikut diverifikasi pada 2026-07-13 melalui registry resmi dan harus dipasang secara exact agar lockfile reproducible:

```text
next 16.2.10                    fastapi 0.139.0
react/react-dom 19.2.7          pydantic 2.13.4
typescript 7.0.2                pydantic-settings 2.14.2
tailwindcss 4.3.2               sqlalchemy 2.0.51
@tanstack/react-query 5.101.2   alembic 1.18.5
react-hook-form 7.81.0          asyncpg 0.31.0
zod 4.4.3                       httpx 0.28.1
vitest 4.1.10                   pytest 9.1.1
@playwright/test 1.61.1         pytest-asyncio 1.4.0
eslint 10.7.0                   ruff 0.15.21
prettier 3.9.5                  mypy 2.3.0
openapi-typescript 7.13.0       structlog 26.1.0
caddy 2.11.4-alpine             postgres 18.4-alpine
redis 8.8.0-alpine              minio RELEASE.2025-09-07T16-13-09Z
minio/mc RELEASE.2025-08-13T08-35-41Z
```

---

### Task 1: Establish repository governance and workspaces

**Files:**
- Create: `AGENTS.md`
- Create: `.editorconfig`
- Modify: `.gitignore`
- Create: `package.json`
- Create: `docs/assumptions.md`
- Create: `docs/architecture.md`
- Create: `docs/implementation-plan.md`

- [ ] **Step 1: Write the repository rules**

Create `AGENTS.md`:

```md
# AGENTS.md

## Mission
Build and maintain Jepret, a mobile-first marketplace for clients and visual creators.

## Working rules
- Inspect existing code before editing.
- Keep the architecture a modular monolith.
- Prefer simple, maintainable solutions over clever abstractions.
- Do not leave core paths as mocks or TODOs.
- Payment may use a mock/sandbox adapter, but the business state machine must be complete.
- Never commit secrets.
- Use stable, non-deprecated APIs.
- Preserve backward compatibility unless a migration is included.
- Every database change requires an Alembic migration.
- Every authorization-sensitive feature requires backend permission tests.
- Every booking/payment change requires transaction and idempotency review.

## Language
- Code, identifiers, schema, and technical comments: English.
- User-facing UI: Indonesian.
- Documentation: Indonesian, with English technical terms where clearer.

## Frontend
- TypeScript strict mode.
- Accessible components.
- Mobile-first.
- Handle loading, empty, error, and success states.
- Do not fetch protected data directly from client code without the approved API/auth flow.
- Keep feature code grouped by domain.

## Backend
- Keep route handlers thin.
- Put domain rules in testable services.
- Validate inputs and authorize every action.
- Use consistent API errors.
- Avoid N+1 queries.
- Use transactions for booking, payment, review, and availability-sensitive operations.

## Quality gates
Before declaring a task complete:
1. Run formatter.
2. Run lint.
3. Run type-check.
4. Run relevant unit/integration tests.
5. Run build.
6. Review the diff for security and accidental secrets.
7. Update docs when behavior or setup changes.
8. Run `npm run verify` from the repository root before declaring Phase 1 work complete.

## Reporting
At the end of each task, report:
- summary
- files changed
- migrations
- tests run and results
- known limitations
- next recommended task
```

- [ ] **Step 2: Add cross-platform editor and ignore rules**

Create `.editorconfig`:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
indent_style = space
indent_size = 2
trim_trailing_whitespace = true

[*.py]
indent_size = 4

[Makefile]
indent_style = tab
```

Append these entries to `.gitignore` while preserving `.superpowers/`:

```gitignore
.env
.env.*
!.env.example
node_modules/
.next/
coverage/
playwright-report/
test-results/
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.pyc
postgres-data/
minio-data/
```

- [ ] **Step 3: Create the root npm workspace**

Create `package.json`:

```json
{
  "name": "jepret",
  "private": true,
  "version": "0.1.0",
  "engines": { "node": ">=24 <25" },
  "workspaces": ["apps/web", "packages/contracts"],
  "devDependencies": { "prettier": "3.9.5" },
  "scripts": {
    "format": "node scripts/verify.mjs format",
    "format:check": "node scripts/verify.mjs formatcheck",
    "lint": "node scripts/verify.mjs lint",
    "typecheck": "node scripts/verify.mjs typecheck",
    "test": "node scripts/verify.mjs test",
    "build": "node scripts/verify.mjs build",
    "verify": "node scripts/verify.mjs verify",
    "contracts:generate": "npm --workspace @jepret/contracts run generate",
    "contracts:check": "npm --workspace @jepret/contracts run check"
  }
}
```

- [ ] **Step 4: Record Phase 0 assumptions and decisions**

Create `docs/assumptions.md` with these explicit decisions:

```md
# Asumsi Jepret Phase 0–1

- Target pertama adalah local development dan CI, bukan cloud production.
- Smartphone PWA adalah client utama; desktop memakai codebase yang sama.
- Caddy adalah same-origin gateway.
- PostgreSQL adalah source of truth.
- MinIO hanya storage provider lokal; private URL selalu signed pada fase fitur.
- Redis opsional dan tidak boleh diperlukan oleh stack dasar.
- Authentication, marketplace, booking, payment, chat, dan admin tidak termasuk Phase 1.
- UI memakai Bahasa Indonesia; code dan identifier memakai Bahasa Inggris.
- Datetime disimpan UTC dan kelak ditampilkan dengan zona Asia/Jakarta.
```

Create `docs/implementation-plan.md`:

```md
# Progress Implementasi Jepret

- [x] Phase 0 — Discovery dan design approval
- [ ] Phase 1 — Foundation
  - [ ] Governance dan workspace
  - [ ] API system foundation
  - [ ] Database dan migration baseline
  - [ ] Generated contracts
  - [ ] Mobile-first web shell
  - [ ] Local Docker stack
  - [ ] CI dan final verification
- [ ] Phase 2 — Auth dan profiles
- [ ] Phase 3 — Marketplace
- [ ] Phase 4 — Booking
- [ ] Phase 5 — Payment
- [ ] Phase 6 — Chat dan deliverables
- [ ] Phase 7 — Completion, reviews, disputes, admin
- [ ] Phase 8 — Hardening
```

Create `docs/architecture.md`:

````md
# Arsitektur Jepret

## Runtime foundation

```mermaid
flowchart TD
  PWA["Mobile-first Next.js PWA"] --> Caddy
  Caddy -->|/| Web[Next.js]
  Caddy -->|/api/v1/*| API[FastAPI]
  Caddy -->|/ws/*| API
  API --> DB[(PostgreSQL)]
  API --> MinIO
  API -. opsional .-> Redis
```

## ADR-001: Same-origin Caddy gateway

**Status:** Accepted

Caddy menjadi entry point tunggal agar cookie, CSRF, REST, dan WebSocket memiliki perilaku origin yang konsisten. PostgreSQL dan MinIO tetap internal; direct debug port memakai compose override eksplisit.
````

- [ ] **Step 5: Validate text files**

Run:

```powershell
git diff --check
rg -n "TBD|TODO|FIXME" AGENTS.md docs package.json .editorconfig
```

Expected: `git diff --check` exits 0 and `rg` returns no matches.

- [ ] **Step 6: Commit governance**

```bash
git add AGENTS.md .editorconfig .gitignore package.json docs/assumptions.md docs/architecture.md docs/implementation-plan.md
git commit -m "chore: establish Jepret repository governance"
```

---

### Task 2: Scaffold and test validated API settings

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/app/__init__.py`
- Create: `apps/api/app/core/__init__.py`
- Create: `apps/api/app/core/config.py`
- Create: `apps/api/tests/test_config.py`
- Create: `apps/api/uv.lock`

- [ ] **Step 1: Create the Python project definition**

Create `apps/api/pyproject.toml`:

```toml
[project]
name = "jepret-api"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
  "alembic==1.18.5",
  "asyncpg==0.31.0",
  "fastapi==0.139.0",
  "pydantic==2.13.4",
  "pydantic-settings==2.14.2",
  "sqlalchemy[asyncio]==2.0.51",
  "structlog==26.1.0",
  "uvicorn[standard]==0.51.0"
]

[dependency-groups]
dev = [
  "httpx==0.28.1",
  "mypy==2.3.0",
  "pytest==9.1.1",
  "pytest-asyncio==1.4.0",
  "ruff==0.15.21"
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-m 'not integration'"
markers = ["integration: requires the real PostgreSQL service"]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.13"
strict = true
plugins = ["pydantic.mypy"]
```

Run `uv lock --project apps/api` and commit the generated `apps/api/uv.lock`.

- [ ] **Step 2: Write failing settings tests**

Create `apps/api/tests/test_config.py`:

```python
from pydantic import ValidationError
import pytest

from app.core.config import Environment, Settings


def test_settings_accept_complete_development_environment() -> None:
    settings = Settings(
        environment=Environment.DEVELOPMENT,
        database_url="postgresql+asyncpg://jepret:jepret@db:5432/jepret",
        public_origin="http://localhost:8080",
        minio_endpoint="http://minio:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
    )
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.redis_url is None


def test_settings_reject_wildcard_public_origin() -> None:
    with pytest.raises(ValidationError, match="public_origin"):
        Settings(
            database_url="postgresql+asyncpg://jepret:jepret@db:5432/jepret",
            public_origin="*",
            minio_endpoint="http://minio:9000",
            minio_access_key="minioadmin",
            minio_secret_key="minioadmin",
        )
```

- [ ] **Step 3: Run the settings tests and verify RED**

Run: `uv run --project apps/api pytest apps/api/tests/test_config.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.config'`.

- [ ] **Step 4: Implement the minimal validated settings**

Create `apps/api/app/core/config.py`:

```python
from enum import StrEnum
from functools import lru_cache

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JEPRET_", env_file=".env", extra="ignore")

    environment: Environment = Environment.DEVELOPMENT
    database_url: str
    public_origin: AnyHttpUrl
    minio_endpoint: AnyHttpUrl
    minio_access_key: str = Field(min_length=1)
    minio_secret_key: str = Field(min_length=1)
    redis_url: str | None = None

    @field_validator("public_origin", mode="before")
    @classmethod
    def reject_wildcard_origin(cls, value: object) -> object:
        if value == "*":
            raise ValueError("public_origin cannot be a wildcard")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 5: Run tests, lint, and type-check**

```bash
uv run --project apps/api pytest apps/api/tests/test_config.py -q
uv run --project apps/api ruff check apps/api
uv run --project apps/api mypy apps/api/app
```

Expected: 2 tests pass; Ruff and mypy exit 0.

- [ ] **Step 6: Commit API settings**

```bash
git add apps/api
git commit -m "feat(api): add validated application settings"
```

---

### Task 3: Add API errors, correlation IDs, health, and logging

**Files:**
- Create: `apps/api/app/core/errors.py`
- Create: `apps/api/app/core/logging.py`
- Create: `apps/api/app/core/middleware.py`
- Create: `apps/api/app/api/__init__.py`
- Create: `apps/api/app/api/system.py`
- Create: `apps/api/app/main.py`
- Create: `apps/api/tests/test_system_api.py`

- [ ] **Step 1: Write failing health and correlation tests**

Create `apps/api/tests/test_system_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_consistent_envelope_and_request_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"X-Request-ID": "req-test-123"})

    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok"}}
    assert response.headers["X-Request-ID"] == "req-test-123"


def test_unknown_route_uses_error_envelope() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROUTE_NOT_FOUND"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --project apps/api pytest apps/api/tests/test_system_api.py -q`

Expected: FAIL because `app.main` does not exist.

- [ ] **Step 3: Implement error models and handlers**

Create `apps/api/app/core/errors.py`:

```python
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=ErrorEnvelope(
        error=ErrorBody(code=code, message=message)
    ).model_dump())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, __: RequestValidationError) -> JSONResponse:
        return error_response(422, "REQUEST_VALIDATION_FAILED", "Data permintaan tidak valid.")

    @app.exception_handler(404)
    async def not_found_handler(_: Request, __: Exception) -> JSONResponse:
        return error_response(404, "ROUTE_NOT_FOUND", "Endpoint tidak ditemukan.")
```

- [ ] **Step 4: Implement correlation middleware, logging, and health route**

Create `apps/api/app/core/middleware.py`:

```python
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

Create `apps/api/app/core/logging.py`:

```python
import logging
import structlog


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
```

Create `apps/api/app/api/system.py`:

```python
from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, dict[str, str]]:
    return {"data": {"status": "ok"}}
```

Create `apps/api/app/main.py`:

```python
from fastapi import FastAPI

from app.api.system import router as system_router
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Jepret API", version="0.1.0",
        docs_url="/api/docs", openapi_url="/api/openapi.json",
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)
    app.include_router(system_router)
    return app


app = create_app()
```

- [ ] **Step 5: Run tests and static checks**

```bash
uv run --project apps/api pytest apps/api/tests/test_system_api.py -q
uv run --project apps/api ruff check apps/api
uv run --project apps/api mypy apps/api/app
```

Expected: 2 tests pass; Ruff and mypy exit 0.

- [ ] **Step 6: Commit system API**

```bash
git add apps/api
git commit -m "feat(api): add health errors and correlation IDs"
```

---

### Task 4: Add async database lifecycle, readiness, and Alembic baseline

**Files:**
- Create: `apps/api/app/db/__init__.py`
- Create: `apps/api/app/db/session.py`
- Create: `apps/api/tests/test_readiness.py`
- Create: `apps/api/tests/integration/test_database.py`
- Create: `apps/api/alembic.ini`
- Create: `apps/api/migrations/env.py`
- Create: `apps/api/migrations/script.py.mako`
- Create: `apps/api/migrations/versions/20260713_0001_baseline.py`
- Modify: `apps/api/app/api/system.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Write the failing readiness unit test**

Create `apps/api/tests/test_readiness.py`:

```python
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.db.session import database_ready
from app.main import create_app


def test_readiness_returns_503_when_database_is_unavailable() -> None:
    app = create_app()
    app.dependency_overrides[database_ready] = AsyncMock(return_value=False)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
```

- [ ] **Step 2: Run the unit test and verify RED**

Run: `uv run --project apps/api pytest apps/api/tests/test_readiness.py -q`

Expected: FAIL because `app.db.session` does not exist.

- [ ] **Step 3: Implement the engine and readiness dependency**

Create `apps/api/app/db/session.py`:

```python
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings

_engine: AsyncEngine | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine
    if _engine is None:
        resolved = settings or get_settings()
        _engine = create_async_engine(resolved.database_url, pool_pre_ping=True)
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as session:
        yield session


async def database_ready() -> bool:
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
```

- [ ] **Step 4: Add readiness routing and application shutdown**

Add to `apps/api/app/api/system.py`:

```python
from fastapi import Depends
from fastapi.responses import JSONResponse

from app.core.errors import error_response
from app.db.session import database_ready


@router.get("/ready", response_model=None)
async def ready(is_ready: bool = Depends(database_ready)) -> dict[str, dict[str, str]] | JSONResponse:
    if not is_ready:
        return error_response(503, "DEPENDENCY_UNAVAILABLE", "Layanan belum siap.")
    return {"data": {"status": "ready"}}
```

Replace `apps/api/app/main.py` with the lifespan-aware factory:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.system import router as system_router
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware
from app.db.session import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Jepret API", version="0.1.0", lifespan=lifespan,
        docs_url="/api/docs", openapi_url="/api/openapi.json",
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)
    app.include_router(system_router)
    return app


app = create_app()
```

- [ ] **Step 5: Add the empty Alembic baseline**

Initialize Alembic with:

```bash
cd apps/api
uv run alembic init -t async migrations
```

Then replace the generated URL lookup in `migrations/env.py` with `get_settings().database_url`, and create `migrations/versions/20260713_0001_baseline.py`:

```python
"""Establish empty Phase 1 baseline."""

revision = "20260713_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
```

- [ ] **Step 6: Add the real PostgreSQL integration test**

Create `apps/api/tests/integration/test_database.py`:

```python
import pytest
from sqlalchemy import text

from app.db.session import get_engine


@pytest.mark.integration
async def test_postgres_connection_executes_select_one() -> None:
    async with get_engine().connect() as connection:
        result = await connection.scalar(text("SELECT 1"))
    assert result == 1
```

- [ ] **Step 7: Run the default test suite with integration deselected**

```bash
uv run --project apps/api pytest apps/api/tests/test_readiness.py -q
uv run --project apps/api pytest apps/api/tests -q
```

Expected: unit tests pass and pytest reports the PostgreSQL integration test as deselected. Task 8 runs that test after the Compose database exists.

- [ ] **Step 8: Commit database foundation**

```bash
git add apps/api
git commit -m "feat(api): add database readiness and migration baseline"
```

---

### Task 5: Generate the TypeScript contract from OpenAPI

**Files:**
- Create: `apps/api/scripts/export_openapi.py`
- Create: `packages/contracts/package.json`
- Create: `packages/contracts/openapi.json`
- Create: `packages/contracts/src/schema.d.ts`
- Create: `packages/contracts/src/index.ts`

- [ ] **Step 1: Create the OpenAPI exporter**

Create `apps/api/scripts/export_openapi.py`:

```python
import json
from pathlib import Path

from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.json"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    OUTPUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create the contracts workspace**

Create `packages/contracts/package.json`:

```json
{
  "name": "@jepret/contracts",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "export": "uv run --project ../../apps/api python ../../apps/api/scripts/export_openapi.py",
    "generate": "npm run export && openapi-typescript openapi.json -o src/schema.d.ts",
    "check": "npm run generate && git diff --exit-code -- openapi.json src/schema.d.ts"
  },
  "devDependencies": {
    "openapi-typescript": "7.13.0"
  },
  "exports": { ".": "./src/index.ts" }
}
```

Create `packages/contracts/src/index.ts`:

```ts
export type { paths, components } from "./schema";
```

- [ ] **Step 3: Generate and inspect the contract**

```bash
npm install
npm run contracts:generate
rg -n '"/health"|"/ready"' packages/contracts/openapi.json
```

Expected: both routes appear; `src/schema.d.ts` exports `paths` and `components`.

- [ ] **Step 4: Verify deterministic generation**

Run: `npm run contracts:check`

Expected: exit 0 with no Git diff after regeneration.

- [ ] **Step 5: Commit contracts**

```bash
git add package-lock.json packages/contracts apps/api/scripts/export_openapi.py
git commit -m "feat: generate TypeScript contracts from OpenAPI"
```

---

### Task 6: Scaffold the Next.js test harness and providers

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/next-env.d.ts`
- Create: `apps/web/next.config.ts`
- Create: `apps/web/postcss.config.mjs`
- Create: `apps/web/eslint.config.mjs`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/src/test/setup.ts`
- Create: `apps/web/src/lib/query-provider.tsx`
- Create: `apps/web/src/lib/query-provider.test.tsx`

- [ ] **Step 1: Create pinned frontend package metadata**

Create `apps/web/package.json` with these exact dependencies:

```json
{
  "name": "@jepret/web",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev --hostname 0.0.0.0",
    "build": "next build",
    "start": "next start --hostname 0.0.0.0",
    "lint": "eslint . --max-warnings=0",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@jepret/contracts": "*",
    "@tanstack/react-query": "5.101.2",
    "clsx": "2.1.1",
    "lucide-react": "1.24.0",
    "next": "16.2.10",
    "react": "19.2.7",
    "react-dom": "19.2.7",
    "tailwind-merge": "3.6.0",
    "zod": "4.4.3"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "4.3.2",
    "@testing-library/jest-dom": "6.9.1",
    "@testing-library/react": "16.3.2",
    "@types/node": "24.13.3",
    "@types/react": "19.2.17",
    "@types/react-dom": "19.2.3",
    "eslint": "10.7.0",
    "eslint-config-next": "16.2.10",
    "jsdom": "29.1.1",
    "tailwindcss": "4.3.2",
    "typescript": "7.0.2",
    "vitest": "4.1.10"
  }
}
```

Create `apps/web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

Create `apps/web/next.config.ts`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@jepret/contracts"],
};

export default nextConfig;
```

Create `apps/web/next-env.d.ts`:

```ts
/// <reference types="next" />
/// <reference types="next/image-types/global" />
```

Create `apps/web/postcss.config.mjs`:

```js
export default { plugins: { "@tailwindcss/postcss": {} } };
```

Create `apps/web/eslint.config.mjs`:

```js
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

export default defineConfig([
  ...nextVitals,
  globalIgnores([".next/**", "coverage/**", "playwright-report/**", "test-results/**"]),
]);
```

- [ ] **Step 2: Write the failing QueryProvider test**

Create `apps/web/src/lib/query-provider.test.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QueryProvider } from "./query-provider";

function Probe() {
  const query = useQuery({ queryKey: ["probe"], queryFn: async () => "siap" });
  return <span>{query.data ?? "memuat"}</span>;
}

describe("QueryProvider", () => {
  it("provides a query client", async () => {
    render(<QueryProvider><Probe /></QueryProvider>);
    expect(await screen.findByText("siap")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the test and verify RED**

Run: `npm --workspace @jepret/web test -- query-provider.test.tsx`

Expected: FAIL because `query-provider.tsx` does not exist.

- [ ] **Step 4: Implement the provider and test configuration**

Create `apps/web/src/lib/query-provider.tsx`:

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
  }));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
```

Create `apps/web/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

Create `apps/web/vitest.config.ts`:

```ts
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] },
  resolve: { alias: { "@": path.resolve(dirname, "src") } },
});
```

- [ ] **Step 5: Run frontend test and type-check**

```bash
npm install
npm --workspace @jepret/web test
npm --workspace @jepret/web run typecheck
```

Expected: QueryProvider test passes and TypeScript exits 0.

- [ ] **Step 6: Commit web harness**

```bash
git add apps/web package-lock.json
git commit -m "chore(web): scaffold Next.js testing foundation"
```

---

### Task 7: Build the tested mobile-first application shell

**Files:**
- Create: `apps/web/src/app/globals.css`
- Create: `apps/web/src/app/layout.tsx`
- Create: `apps/web/src/app/page.tsx`
- Create: `apps/web/src/app/loading.tsx`
- Create: `apps/web/src/app/error.tsx`
- Create: `apps/web/src/components/layout/app-header.tsx`
- Create: `apps/web/src/components/layout/bottom-navigation.tsx`
- Create: `apps/web/src/components/creators/creator-preview-card.tsx`
- Create: `apps/web/src/app/page.test.tsx`

- [ ] **Step 1: Write the failing mobile shell test**

Create `apps/web/src/app/page.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("HomePage", () => {
  it("renders Indonesian discovery content and client navigation", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { name: /cerita yang layak diingat/i })).toBeVisible();
    expect(screen.getByRole("searchbox", { name: /cari kreator/i })).toHaveClass("min-h-11");
    expect(screen.getByRole("navigation", { name: /navigasi utama/i })).toBeVisible();
    expect(screen.getByText("Studio Cahaya")).toBeVisible();
  });
});
```

- [ ] **Step 2: Run the page test and verify RED**

Run: `npm --workspace @jepret/web test -- page.test.tsx`

Expected: FAIL because `page.tsx` and shell components do not exist.

- [ ] **Step 3: Define semantic design tokens**

Create `apps/web/src/app/globals.css`:

```css
@import "tailwindcss";

:root {
  --background: #171614;
  --foreground: #f7f1e7;
  --surface: #f5efe5;
  --surface-foreground: #191714;
  --muted: #786f64;
  --border: #d8ccbc;
  --primary: #c58b32;
  --primary-foreground: #17120b;
  --success: #6f7c5e;
  --warning: #b97828;
  --destructive: #b8493f;
}

* { box-sizing: border-box; }
body { margin: 0; background: var(--background); color: var(--foreground); }
:focus-visible { outline: 3px solid var(--primary); outline-offset: 3px; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; }
}
```

- [ ] **Step 4: Implement the shell components**

Create `apps/web/src/components/layout/app-header.tsx`:

```tsx
export function AppHeader() {
  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="mx-auto flex min-h-14 max-w-6xl items-center justify-between px-5">
        <span className="text-sm font-bold tracking-[0.18em]">JEPRET</span>
        <span className="text-sm text-[var(--muted)]">Bandung</span>
      </div>
    </header>
  );
}
```

Create `apps/web/src/components/layout/bottom-navigation.tsx`:

```tsx
import { CalendarDays, Compass, MessageCircle, UserRound } from "lucide-react";

const items = [
  ["Jelajah", Compass], ["Booking", CalendarDays], ["Chat", MessageCircle], ["Profil", UserRound],
] as const;

export function BottomNavigation() {
  return (
    <nav aria-label="Navigasi utama" className="fixed inset-x-0 bottom-0 border-t border-[var(--border)] bg-[var(--surface)] md:hidden">
      <ul className="mx-auto grid max-w-md grid-cols-4">
        {items.map(([label, Icon]) => (
          <li key={label}><span className="flex min-h-14 flex-col items-center justify-center gap-1 text-xs"><Icon aria-hidden size={18} />{label}</span></li>
        ))}
      </ul>
    </nav>
  );
}
```

Create `apps/web/src/components/creators/creator-preview-card.tsx` without a fake action:

```tsx
export function CreatorPreviewCard() {
  return (
    <article className="mt-4 max-w-sm overflow-hidden rounded-2xl bg-[var(--background)] text-[var(--foreground)]">
      <div aria-hidden className="h-40 bg-[linear-gradient(135deg,#5b5148,#1f1d1b)]" />
      <div className="p-4">
        <p className="text-xs font-semibold text-[var(--primary)]">TERVERIFIKASI</p>
        <h3 className="mt-2 text-lg font-semibold">Studio Cahaya</h3>
        <p className="mt-1 text-sm text-[#cfc5b8]">Bandung · Wedding · ★ 4,9</p>
        <p className="mt-4 text-sm">Mulai Rp1.500.000</p>
      </div>
    </article>
  );
}
```

Implement `page.tsx` with this semantic skeleton:

```tsx
import { AppHeader } from "@/components/layout/app-header";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import { CreatorPreviewCard } from "@/components/creators/creator-preview-card";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[var(--surface)] text-[var(--surface-foreground)] pb-24">
      <AppHeader />
      <section className="mx-auto max-w-6xl px-5 py-10">
        <p className="text-xs uppercase tracking-[0.18em] text-[var(--primary)]">Jepret</p>
        <h1 className="max-w-xl font-serif text-5xl leading-none">Cerita yang layak diingat.</h1>
        <p className="mt-5 max-w-xl text-[var(--muted)]">Temukan fotografer dan videografer terverifikasi untuk setiap momen.</p>
        <label className="mt-7 block max-w-xl">
          <span className="sr-only">Cari kreator</span>
          <input type="search" aria-label="Cari kreator" className="min-h-11 w-full rounded-xl border border-[var(--border)] bg-white px-4" placeholder="Cari gaya, kota, atau kebutuhan" />
        </label>
      </section>
      <section aria-labelledby="creator-heading" className="mx-auto max-w-6xl px-5">
        <h2 id="creator-heading" className="font-serif text-2xl">Pilihan di dekatmu</h2>
        <CreatorPreviewCard />
      </section>
      <BottomNavigation />
    </main>
  );
}
```

Create `apps/web/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { QueryProvider } from "@/lib/query-provider";
import "./globals.css";

export const metadata: Metadata = { title: "Jepret", description: "Temukan kreator visual untuk momenmu." };

export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="id"><body><QueryProvider>{children}</QueryProvider></body></html>;
}
```

Create `apps/web/src/app/loading.tsx`:

```tsx
export default function Loading() {
  return <main aria-busy="true" aria-label="Memuat halaman" className="min-h-screen animate-pulse bg-[var(--surface)]" />;
}
```

Create `apps/web/src/app/error.tsx`:

```tsx
"use client";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="grid min-h-screen place-items-center bg-[var(--surface)] px-5 text-[var(--surface-foreground)]">
      <div><h1 className="font-serif text-3xl">Halaman belum dapat dimuat.</h1><p className="mt-3 text-[var(--muted)]">Silakan coba kembali.</p><button className="mt-6 min-h-11 rounded-xl bg-[var(--primary)] px-5" onClick={reset}>Coba lagi</button></div>
    </main>
  );
}
```

- [ ] **Step 5: Run component, lint, type, and production build checks**

```bash
npm --workspace @jepret/web test
npm --workspace @jepret/web run lint
npm --workspace @jepret/web run typecheck
npm --workspace @jepret/web run build
```

Expected: all tests pass, ESLint has 0 warnings, TypeScript exits 0, Next.js build succeeds.

- [ ] **Step 6: Commit mobile shell**

```bash
git add apps/web
git commit -m "feat(web): add mobile-first Jepret shell"
```

---

### Task 8: Containerize the required local stack behind Caddy

**Files:**
- Create: `.env.example`
- Create: `apps/api/Dockerfile`
- Create: `apps/web/Dockerfile`
- Create: `infra/gateway/Caddyfile`
- Create: `docker-compose.yml`
- Create: `docker-compose.debug.yml`
- Modify: `apps/api/app/api/system.py`
- Create: `apps/api/tests/test_websocket_probe.py`

- [ ] **Step 1: Write the failing WebSocket probe test**

Create `apps/api/tests/test_websocket_probe.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_development_websocket_probe_sends_status_and_closes() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws/health") as websocket:
            assert websocket.receive_json() == {"status": "ok"}
```

- [ ] **Step 2: Run test and verify RED**

Run: `uv run --project apps/api pytest apps/api/tests/test_websocket_probe.py -q`

Expected: FAIL because `/ws/health` does not exist.

- [ ] **Step 3: Add the infrastructure-only WebSocket probe**

Add to `apps/api/app/api/system.py`:

```python
from fastapi import WebSocket


@router.websocket("/ws/health")
async def websocket_health(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"status": "ok"})
    await websocket.close()
```

Document that this route validates gateway upgrade forwarding only; authenticated business WebSockets are added during the chat phase.

- [ ] **Step 4: Create service Dockerfiles**

Create `apps/api/Dockerfile`:

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `apps/web/Dockerfile`:

```dockerfile
FROM node:24-alpine AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci

FROM node:24-alpine AS builder
WORKDIR /repo
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /repo/node_modules ./node_modules
COPY . .
RUN npm --workspace @jepret/web run build

FROM node:24-alpine AS runner
WORKDIR /repo
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next/static ./apps/web/.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
```

- [ ] **Step 5: Configure Caddy routing**

Create `infra/gateway/Caddyfile`:

```caddyfile
:80 {
  encode zstd gzip

  handle /health {
    reverse_proxy api:8000
  }

  handle /ready {
    reverse_proxy api:8000
  }

  handle /api/v1/* {
    reverse_proxy api:8000
  }

  handle /api/docs* {
    reverse_proxy api:8000
  }

  handle /api/openapi.json {
    reverse_proxy api:8000
  }

  handle /ws/* {
    reverse_proxy api:8000
  }

  handle {
    reverse_proxy web:3000
  }
}
```

System routes tetap tersedia sebagai `/health` dan `/ready`. Prefix `/api/v1/*` dipertahankan utuh untuk business routes pada fase berikutnya.

- [ ] **Step 6: Define environment values and Compose services**

Create `.env.example`:

```dotenv
JEPRET_ENVIRONMENT=development
JEPRET_DATABASE_URL=postgresql+asyncpg://jepret:jepret@db:5432/jepret
JEPRET_PUBLIC_ORIGIN=http://localhost:8080
JEPRET_MINIO_ENDPOINT=http://minio:9000
JEPRET_MINIO_ACCESS_KEY=minioadmin
JEPRET_MINIO_SECRET_KEY=minioadmin
JEPRET_REDIS_URL=
POSTGRES_DB=jepret
POSTGRES_USER=jepret
POSTGRES_PASSWORD=jepret
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
```

Create `docker-compose.yml`:

```yaml
services:
  gateway:
    image: caddy:2.11.4-alpine
    ports: ["8080:80"]
    volumes:
      - ./infra/gateway/Caddyfile:/etc/caddy/Caddyfile:ro
    depends_on:
      api: { condition: service_healthy }
      web: { condition: service_started }

  web:
    build:
      context: .
      dockerfile: apps/web/Dockerfile
    expose: ["3000"]

  api:
    build:
      context: apps/api
      dockerfile: Dockerfile
    environment: &api-environment
      JEPRET_ENVIRONMENT: development
      JEPRET_DATABASE_URL: postgresql+asyncpg://jepret:jepret@db:5432/jepret
      JEPRET_PUBLIC_ORIGIN: http://localhost:8080
      JEPRET_MINIO_ENDPOINT: http://minio:9000
      JEPRET_MINIO_ACCESS_KEY: ${MINIO_ROOT_USER:-minioadmin}
      JEPRET_MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-minioadmin}
    expose: ["8000"]
    depends_on:
      db: { condition: service_healthy }
      minio-init: { condition: service_completed_successfully }
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 5s
      timeout: 3s
      retries: 12

  migrate:
    build:
      context: apps/api
      dockerfile: Dockerfile
    profiles: ["tools"]
    environment: *api-environment
    command: ["uv", "run", "--no-dev", "alembic", "upgrade", "head"]
    depends_on:
      db: { condition: service_healthy }

  db:
    image: postgres:18.4-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-jepret}
      POSTGRES_USER: ${POSTGRES_USER:-jepret}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-jepret}
    volumes: ["postgres_data:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 12

  minio:
    image: minio/minio:RELEASE.2025-09-07T16-13-09Z
    command: server /data --console-address :9001
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}
    volumes: ["minio_data:/data"]
    expose: ["9000", "9001"]

  minio-init:
    image: minio/mc:RELEASE.2025-08-13T08-35-41Z
    depends_on: [minio]
    entrypoint: ["/bin/sh", "-c"]
    command:
      - >-
        until mc alias set local http://minio:9000 $${MINIO_ROOT_USER} $${MINIO_ROOT_PASSWORD}; do sleep 2; done;
        mc mb --ignore-existing local/jepret-public;
        mc mb --ignore-existing local/jepret-private
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}

  redis:
    image: redis:8.8.0-alpine
    profiles: ["optional"]
    command: ["redis-server", "--save", ""]
    expose: ["6379"]

volumes:
  postgres_data:
  minio_data:
```

Create `docker-compose.debug.yml` for explicit direct-access debugging:

```yaml
services:
  db:
    ports: ["127.0.0.1:5432:5432"]
  minio:
    ports: ["127.0.0.1:9000:9000", "127.0.0.1:9001:9001"]
```

- [ ] **Step 7: Validate Compose and run the stack**

```bash
docker compose config --quiet
docker compose build
docker compose run --rm migrate
docker compose up -d
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d db
docker compose ps
```

Expected: config and build succeed; migration exits 0; gateway, web, API, db, and MinIO are healthy; Redis is absent.

- [ ] **Step 8: Probe same-origin routes**

```powershell
Invoke-WebRequest http://localhost:8080 -UseBasicParsing | Select-Object StatusCode
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/ready
```

Expected: homepage status 200; health is `{"data":{"status":"ok"}}`; readiness is `{"data":{"status":"ready"}}`.

Run the integration test now that PostgreSQL exists:

```powershell
$env:JEPRET_DATABASE_URL='postgresql+asyncpg://jepret:jepret@localhost:5432/jepret'
$env:JEPRET_PUBLIC_ORIGIN='http://localhost:8080'
$env:JEPRET_MINIO_ENDPOINT='http://localhost:9000'
$env:JEPRET_MINIO_ACCESS_KEY='minioadmin'
$env:JEPRET_MINIO_SECRET_KEY='minioadmin'
uv run --project apps/api pytest -m integration apps/api/tests/integration/test_database.py -q
```

Expected: the PostgreSQL integration test passes.

- [ ] **Step 9: Commit local runtime**

```bash
git add .env.example apps/api apps/web infra docker-compose.yml docker-compose.debug.yml
git commit -m "feat(infra): add same-origin local Docker stack"
```

---

### Task 9: Add cross-platform quality commands

**Files:**
- Create: `scripts/verify.mjs`
- Create: `Makefile`

- [ ] **Step 1: Create the quality runner**

Create `scripts/verify.mjs`:

```js
import { spawnSync } from "node:child_process";

const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const uv = process.platform === "win32" ? "uv.exe" : "uv";

const groups = {
  format: [[uv, ["run", "--project", "apps/api", "ruff", "format", "apps/api"]], [npm, ["exec", "prettier", "--", "--write", "."]]],
  formatcheck: [[uv, ["run", "--project", "apps/api", "ruff", "format", "--check", "apps/api"]], [npm, ["exec", "prettier", "--", "--check", "."]]],
  lint: [[uv, ["run", "--project", "apps/api", "ruff", "check", "apps/api"]], [npm, ["--workspace", "@jepret/web", "run", "lint"]]],
  typecheck: [[uv, ["run", "--project", "apps/api", "mypy", "apps/api/app"]], [npm, ["--workspace", "@jepret/web", "run", "typecheck"]]],
  test: [[uv, ["run", "--project", "apps/api", "pytest", "apps/api/tests", "-q"]], [npm, ["--workspace", "@jepret/web", "test"]]],
  contracts: [[npm, ["run", "contracts:check"]]],
  build: [[npm, ["--workspace", "@jepret/web", "run", "build"]], ["docker", ["compose", "config", "--quiet"]]],
};

const requested = process.argv[2];
const order = requested === "verify" ? ["formatcheck", "lint", "typecheck", "test", "contracts", "build"] : [requested];
for (const group of order) {
  if (!groups[group]) throw new Error(`Unknown quality group: ${group}`);
  for (const [command, args] of groups[group]) {
    const result = spawnSync(command, args, { stdio: "inherit", shell: false });
    if (result.status !== 0) process.exit(result.status ?? 1);
  }
}
```

- [ ] **Step 2: Create Makefile wrappers**

Create `Makefile`:

```makefile
.PHONY: format lint typecheck test build verify up down migrate

format:
	npm run format
lint:
	npm run lint
typecheck:
	npm run typecheck
test:
	npm test
build:
	npm run build
verify:
	npm run verify
up:
	docker compose up --build
down:
	docker compose down
migrate:
	docker compose run --rm migrate
```

- [ ] **Step 3: Run every quality group independently**

```bash
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
npm run verify
```

Expected: every command exits 0; `verify` stops immediately if any child command is forced to fail.

- [ ] **Step 4: Commit task runner**

```bash
git add package.json package-lock.json scripts/verify.mjs Makefile
git commit -m "chore: add cross-platform quality gates"
```

---

### Task 10: Add Playwright and Compose smoke coverage

**Files:**
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/e2e/foundation.spec.ts`
- Modify: `apps/web/package.json`
- Modify: `scripts/verify.mjs`

- [ ] **Step 1: Install and configure pinned Playwright**

Add `@playwright/test: 1.61.1` to web devDependencies and create `apps/web/playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080", trace: "on-first-retry" },
  projects: [{ name: "mobile-chromium", use: { ...devices["Pixel 7"] } }],
  retries: process.env.CI ? 2 : 0,
});
```

- [ ] **Step 2: Write the failing foundation E2E test**

Create `apps/web/e2e/foundation.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test("mobile shell and API share one origin", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /cerita yang layak diingat/i })).toBeVisible();
  await expect(page.getByRole("navigation", { name: /navigasi utama/i })).toBeVisible();

  const health = await request.get("/health", { headers: { "X-Request-ID": "e2e-request-123" } });
  expect(health.ok()).toBeTruthy();
  await expect(health.json()).resolves.toEqual({ data: { status: "ok" } });
  expect(health.headers()["x-request-id"]).toBe("e2e-request-123");
});

test("gateway forwards WebSocket upgrades", async ({ page }) => {
  const result = await page.evaluate(() => new Promise((resolve, reject) => {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${location.host}/ws/health`);
    socket.onmessage = (event) => resolve(JSON.parse(event.data));
    socket.onerror = () => reject(new Error("WebSocket probe failed"));
  }));
  expect(result).toEqual({ status: "ok" });
});
```

- [ ] **Step 3: Run E2E before the stack and verify RED**

Run: `npm --workspace @jepret/web exec playwright test`

Expected: FAIL with connection refused when the Compose stack is down.

- [ ] **Step 4: Run E2E against Compose and verify GREEN**

```bash
docker compose up -d --build
npm --workspace @jepret/web exec playwright install chromium
npm --workspace @jepret/web exec playwright test
```

Expected: 2 Playwright tests pass on `mobile-chromium`.

- [ ] **Step 5: Add E2E to the explicit smoke command**

Add `"e2e": "playwright test"` to `apps/web/package.json`. Add this entry to `groups` in `scripts/verify.mjs`:

```js
e2e: [[npm, ["--workspace", "@jepret/web", "run", "e2e"]]],
```

Do not put E2E inside the default local `verify`; CI invokes it after starting Compose.

- [ ] **Step 6: Commit E2E coverage**

```bash
git add apps/web package-lock.json scripts/verify.mjs
git commit -m "test: add mobile gateway smoke coverage"
```

---

### Task 11: Add GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the CI workflow**

Create `.github/workflows/ci.yml` with two jobs:

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main, master]

jobs:
  quality:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:18.4-alpine
        env:
          POSTGRES_DB: jepret
          POSTGRES_USER: jepret
          POSTGRES_PASSWORD: jepret
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U jepret -d jepret"
          --health-interval 5s --health-timeout 3s --health-retries 12
    env:
      JEPRET_DATABASE_URL: postgresql+asyncpg://jepret:jepret@localhost:5432/jepret
      JEPRET_PUBLIC_ORIGIN: http://localhost:8080
      JEPRET_MINIO_ENDPOINT: http://localhost:9000
      JEPRET_MINIO_ACCESS_KEY: minioadmin
      JEPRET_MINIO_SECRET_KEY: minioadmin
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: npm
      - uses: astral-sh/setup-uv@v6
        with:
          version: "0.11.28"
          enable-cache: true
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: npm ci
      - run: uv sync --project apps/api --frozen
      - run: uv run --project apps/api ruff format --check apps/api
      - run: npm run verify
      - run: uv run --project apps/api pytest -m integration apps/api/tests/integration/test_database.py -q
      - run: npm run contracts:check

  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: npm
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: docker compose up -d --build
      - run: docker compose run --rm migrate
      - run: npm --workspace @jepret/web run e2e
      - if: always()
        run: docker compose logs --no-color
```

- [ ] **Step 2: Validate workflow syntax and local command parity**

Run:

```bash
npm run verify
npm run contracts:check
docker compose config --quiet
```

Expected: all commands exit 0. Review YAML indentation with `git diff --check`.

- [ ] **Step 3: Commit CI**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add foundation quality pipeline"
```

---

### Task 12: Complete documentation and final verification

**Files:**
- Create: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/implementation-plan.md`
- Create: `docs/testing.md`
- Create: `docs/deployment.md`

- [ ] **Step 1: Write README setup and troubleshooting**

Create `README.md` in Bahasa Indonesia with these exact sections:

```md
# Jepret
## Status fase
## Arsitektur
## Prasyarat
## Menjalankan dengan Docker
## Menjalankan tanpa Docker
## Environment variables
## Migration
## Quality gates
## API docs
## Local object storage
## Akun demo
## Troubleshooting
## Security caveats
## Deployment notes
```

For Phase 1, `Akun demo` must state that demo accounts are introduced in the auth/seed phase and do not yet exist. Document `http://localhost:8080`, `/health`, `/ready`, and FastAPI docs through the gateway.

- [ ] **Step 2: Complete architecture, testing, and deployment notes**

Ensure `docs/architecture.md` contains component, request, planned auth, planned storage, and WebSocket flows. Create `docs/testing.md` with every exact command from this plan and its dependency requirements. Create `docs/deployment.md` that explicitly says production deployment is not performed in Phase 1 and lists future requirements: HTTPS, managed PostgreSQL, S3-compatible object storage, secret manager, migration job, backup, and rollback.

- [ ] **Step 3: Mark Phase 1 tracker complete only after evidence**

Run the complete verification first:

```powershell
npm run format
npm run lint
npm run typecheck
npm test
npm run contracts:check
npm run build
docker compose down -v
docker compose up -d --build
docker compose run --rm migrate
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d db
$env:JEPRET_DATABASE_URL='postgresql+asyncpg://jepret:jepret@localhost:5432/jepret'
$env:JEPRET_PUBLIC_ORIGIN='http://localhost:8080'
$env:JEPRET_MINIO_ENDPOINT='http://localhost:9000'
$env:JEPRET_MINIO_ACCESS_KEY='minioadmin'
$env:JEPRET_MINIO_SECRET_KEY='minioadmin'
uv run --project apps/api pytest -m integration apps/api/tests/integration/test_database.py -q
npm --workspace @jepret/web run e2e
git diff --check
git status --short
```

Expected:

- format completes and the subsequent `git diff --check` is clean;
- lint and type-check exit 0;
- all backend and frontend tests pass;
- contract check produces no diff;
- web and container builds succeed;
- migration succeeds from empty volumes;
- both E2E tests pass;
- no secret or untracked generated output appears in `git status`.

Only then update `docs/implementation-plan.md` to mark Phase 1 complete and record the command results.

- [ ] **Step 4: Review the final diff for secrets and scope leakage**

```bash
git diff --check
git grep -n -I -E '(password|secret|token|api[_-]?key)\s*[:=]\s*[^${[:space:]]+' -- ':!package-lock.json' ':!.env.example'
rg -n "TODO|FIXME|TBD" apps packages infra docs README.md
```

Expected: no real credential matches; no core placeholder markers; only documented development defaults exist in `.env.example`.

- [ ] **Step 5: Commit documentation and Phase 1 evidence**

```bash
git add README.md docs
git commit -m "docs: complete Jepret foundation guidance"
```

- [ ] **Step 6: Record final handoff**

Report:

```text
Summary: Phase 0–1 foundation delivered
Migrations: 20260713_0001 baseline
Tests: exact passing counts from pytest, Vitest, and Playwright
Quality: lint, format check, type-check, contract check, and builds
Known limitations: all Phase 2+ business features remain intentionally absent
Next recommended task: brainstorm authentication and client/creator profiles
```
