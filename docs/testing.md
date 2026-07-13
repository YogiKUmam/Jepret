# Panduan Testing Jepret

Seluruh perintah dijalankan dari root repository kecuali disebutkan lain.

## Dependency

- Node.js 24 + npm (`npm install` di root memasang seluruh workspace).
- uv 0.11+ (`uv sync --project apps/api` memasang dependency Python, termasuk dev group).
- Docker Compose v2 untuk integration test dan E2E.
- Browser Playwright: `npm --workspace @jepret/web exec playwright install chromium`.

## Backend (pytest)

```bash
uv run --project apps/api pytest apps/api/tests -q
```

Marker `integration` di-deselect secara default (`addopts = "-m 'not integration'"`). Menjalankan integration test membutuhkan PostgreSQL aktif dan environment berikut:

```powershell
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d db
$env:JEPRET_DATABASE_URL='postgresql+asyncpg://jepret:jepret@localhost:5432/jepret'
$env:JEPRET_PUBLIC_ORIGIN='http://localhost:8080'
$env:JEPRET_MINIO_ENDPOINT='http://localhost:9000'
$env:JEPRET_MINIO_ACCESS_KEY='minioadmin'
$env:JEPRET_MINIO_SECRET_KEY='minioadmin'
uv run --project apps/api pytest -m integration apps/api/tests/integration/test_database.py -q
```

## Backend static checks

```bash
uv run --project apps/api ruff check apps/api
uv run --project apps/api ruff format --check apps/api
uv run --project apps/api mypy apps/api/app
```

## Frontend (Vitest)

```bash
npm --workspace @jepret/web test
npm --workspace @jepret/web run lint
npm --workspace @jepret/web run typecheck
npm --workspace @jepret/web run build
```

## Contracts

```bash
npm run contracts:generate   # export OpenAPI + generate schema.d.ts
npm run contracts:check      # gagal bila hasil generate berbeda dengan commit
```

Membutuhkan uv (untuk export dari FastAPI) dan npm workspace terpasang.

## E2E (Playwright)

Stack Compose harus berjalan terlebih dahulu:

```bash
docker compose up -d --build
docker compose run --rm migrate
npm --workspace @jepret/web exec playwright install chromium
npm --workspace @jepret/web run e2e
```

Base URL default `http://localhost:8080` (override dengan `E2E_BASE_URL`). E2E tidak termasuk `npm run verify`; jalankan eksplisit atau lewat CI.

## Runner gabungan

```bash
npm run verify   # formatcheck → lint → typecheck → test → contracts → build
```

`verify` berhenti pada kegagalan pertama. Group individual: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npm run format`, `npm run format:check`, dan `node scripts/verify.mjs e2e`.
