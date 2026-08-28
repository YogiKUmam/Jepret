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

Marker `integration` di-deselect secara default (`addopts = "-m 'not integration'"`). Dari clean checkout, nyalakan PostgreSQL dan MinIO, tunggu initializer bucket privat selesai, lalu isi seluruh environment berikut:

```powershell
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d db minio minio-init
docker compose -f docker-compose.yml -f docker-compose.debug.yml wait minio-init
docker compose -f docker-compose.yml -f docker-compose.debug.yml ps -a db minio minio-init
$env:JEPRET_ENVIRONMENT='test'
$env:JEPRET_DATABASE_URL='postgresql+asyncpg://jepret:jepret@localhost:15432/jepret'
$env:JEPRET_PUBLIC_ORIGIN='http://localhost:8080'
$env:JEPRET_MINIO_ENDPOINT='http://localhost:9000'
$env:JEPRET_MINIO_PUBLIC_ENDPOINT='http://localhost:9000'
$env:JEPRET_MINIO_ACCESS_KEY='minioadmin'
$env:JEPRET_MINIO_SECRET_KEY='minioadmin'
$env:JEPRET_MINIO_PRIVATE_BUCKET='jepret-private'
Push-Location apps/api
uv run alembic upgrade head
Pop-Location
uv run --project apps/api pytest -m integration apps/api/tests -q
```

Perintah `wait minio-init` harus selesai dengan exit code 0; output `ps -a` harus menunjukkan `minio-init` berstatus `Exited (0)`. Signed browser PUT wajib mengirim `Content-Type` yang ditandatangani dan `If-None-Match: *` agar upload bersifat create-only.

Catatan: menjalankan `docker compose up -d` tanpa file debug dapat me-recreate `db` dan menghapus mapping port 15432 — jalankan ulang perintah override bila koneksi ditolak. API MinIO tetap tersedia hanya melalui loopback `localhost:9000` pada base Compose.

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

## Focused workspace & chat suites

Unit test storage adapter dan rate limiter:

```bash
uv run --project apps/api pytest apps/api/tests/test_storage_adapter.py apps/api/tests/test_rate_limit.py -q
```

Integration API workspace, uploads, conversations, WebSocket, dan deliverables:

```bash
uv run --project apps/api pytest apps/api/tests/test_bookings_api.py apps/api/tests/test_payments_api.py apps/api/tests/test_uploads_api.py apps/api/tests/test_conversations_api.py apps/api/tests/test_conversation_websocket.py apps/api/tests/test_deliverables_api.py apps/api/tests/test_workspace_lifecycle.py apps/api/tests/test_storage_integration.py -m integration -q
```

Frontend workspace & conversation tests:

```bash
npm --workspace @jepret/web test -- src/app/booking/[id]/page.test.tsx src/lib/conversations.test.tsx src/lib/uploads.test.ts
```

Focused E2E workspace lifecycle:

```bash
npm --workspace @jepret/web run e2e -- workspace.spec.ts
```

## Phase 7: Reviews, Disputes & Admin Governance tests

Backend reviews, disputes, and admin API tests:

```bash
uv run --project apps/api pytest apps/api/tests/test_phase7_schema.py apps/api/tests/test_reviews_api.py apps/api/tests/test_disputes_api.py -q
```

Frontend reviews & admin tests:

```bash
npm --workspace @jepret/web test -- src/components/reviews/review-form.test.tsx src/components/disputes/dispute-modal.test.tsx src/app/admin/page.test.tsx src/app/admin/kreator/page.test.tsx src/app/admin/sengketa/page.test.tsx
```

Focused Phase 7 E2E:

```bash
npm --workspace @jepret/web run e2e -- governance.spec.ts
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
docker compose run --rm seed
npm --workspace @jepret/web exec playwright install chromium
npm --workspace @jepret/web run e2e
```

## Matrix verifikasi penuh

```bash
npm run verify
```

Perintah di atas menjalankan: format check, lint, typecheck, unit test backend & frontend, OpenAPI contracts check, dan build.
