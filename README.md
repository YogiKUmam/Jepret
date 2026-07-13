# Jepret

Marketplace mobile-first untuk menghubungkan klien dengan kreator visual (fotografer dan videografer) terverifikasi.

## Status fase

Phase 1 — Foundation. Seluruh fitur bisnis (auth, marketplace, booking, payment, chat, admin) belum ada dan menyusul pada Phase 2+. Lihat `docs/implementation-plan.md` untuk tracker lengkap.

## Arsitektur

Modular monolith dengan same-origin gateway. Caddy menjadi entry point tunggal pada `http://localhost:8080`: route `/` diteruskan ke Next.js, `/api/v1/*`, `/health`, `/ready`, `/api/docs`, dan `/ws/*` diteruskan ke FastAPI. PostgreSQL adalah source of truth; MinIO menyediakan object storage lokal; Redis bersifat opsional (profile `optional`). Detail dan ADR ada di `docs/architecture.md`.

## Prasyarat

Docker Desktop (atau Docker Engine + Compose v2), Node.js 24, npm 10+, dan uv 0.11+. Python 3.13 diunduh otomatis oleh uv. Untuk pengembangan tanpa Docker, PostgreSQL 18 dan MinIO harus tersedia sendiri.

## Menjalankan dengan Docker

```bash
docker compose up -d --build
docker compose run --rm migrate
```

Aplikasi tersedia pada `http://localhost:8080`. Untuk akses langsung PostgreSQL/MinIO saat debugging gunakan override eksplisit:

```bash
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d db minio
```

## Menjalankan tanpa Docker

```bash
npm install
uv sync --project apps/api
npm --workspace @jepret/web run dev          # web pada :3000
uv run --project apps/api uvicorn app.main:app --reload --port 8000
```

Tanpa gateway, web dan API berjalan pada origin berbeda; gunakan mode ini hanya untuk iterasi cepat komponen tunggal.

## Environment variables

Salin `.env.example` menjadi `.env` lalu sesuaikan. Seluruh variable API memakai prefix `JEPRET_`. Tidak ada secret asli di repository; nilai default hanya untuk pengembangan lokal.

## Migration

Setiap perubahan database memakai Alembic. Baseline kosong: `20260713_0001`.

```bash
docker compose run --rm migrate                          # via Docker
uv run --project apps/api alembic upgrade head           # langsung (butuh JEPRET_DATABASE_URL)
```

## Quality gates

```bash
npm run verify          # format check, lint, type-check, test, contracts, build
npm run format          # tulis format (ruff + prettier)
npm test                # pytest + vitest
npm run contracts:check # kontrak OpenAPI deterministik
```

Detail per perintah ada di `docs/testing.md`.

## API docs

Melalui gateway: `http://localhost:8080/api/docs` (Swagger UI) dan `http://localhost:8080/api/openapi.json`. Health check: `/health`; readiness: `/ready`.

## Local object storage

MinIO berjalan internal pada jaringan Compose. Bucket `jepret-public` dan `jepret-private` dibuat otomatis oleh service `minio-init`. Console MinIO hanya dapat diakses melalui override debug pada `http://localhost:9001`. Private URL akan selalu signed pada fase fitur.

## Akun demo

Belum ada. Akun demo diperkenalkan pada fase auth/seed (Phase 2) dan tidak tersedia pada Phase 1.

## Troubleshooting

- **Port 8080 terpakai** — hentikan proses lain atau ubah mapping `gateway.ports` di `docker-compose.yml`.
- **`/ready` mengembalikan 503** — database belum siap; cek `docker compose ps` dan `docker compose logs db`.
- **Migration gagal** — pastikan service `db` sehat lalu ulangi `docker compose run --rm migrate`.
- **Build web gagal di Docker** — pastikan `package-lock.json` ada dan sinkron (`npm install` di root).
- **Test integration Postgres deselected** — memang default; jalankan dengan `-m integration` setelah database tersedia.

## Security caveats

Kredensial default (`minioadmin`, `jepret`) hanya untuk pengembangan lokal dan tidak boleh dipakai di production. Belum ada authentication; jangan mengekspos stack ini ke jaringan publik. Wildcard `public_origin` ditolak oleh validasi settings.

## Deployment notes

Production deployment tidak dilakukan pada Phase 1. Kebutuhan masa depan didokumentasikan di `docs/deployment.md`.
