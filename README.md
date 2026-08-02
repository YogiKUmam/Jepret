# Jepret

Marketplace mobile-first untuk menghubungkan klien dengan kreator visual (fotografer dan videografer) terverifikasi.

## Status fase

Phase 1–5 sudah selesai: foundation, auth dan profiles, marketplace, booking,
serta payment sandbox. Chat, deliverables, reviews, disputes, dan hardening
masih mengikuti Phase 6–8. Lihat `docs/implementation-plan.md` untuk bukti
verifikasi dan tracker lengkap.

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

Setiap perubahan database memakai Alembic. Baseline kosong adalah
`20260713_0001`; migration head saat ini `20260731_0005`.

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

Jalankan seeding setelah migration (khusus lokal):

```bash
docker compose run --rm seed
```

| Peran   | Email                | Password     |
| ------- | -------------------- | ------------ |
| Admin   | admin@jepret.local   | admin12345   |
| Klien   | klien@jepret.local   | klien12345   |
| Kreator | kreator@jepret.local | kreator12345 |

Kreator demo sudah berstatus terverifikasi (Studio Cahaya). Seed juga membuat 7 kreator terverifikasi tambahan untuk marketplace (`kreator2@jepret.local` s.d. `kreator8@jepret.local`, password `kreator12345`). Kredensial ini hanya untuk pengembangan lokal dan tidak boleh dipakai di lingkungan publik.

## Payment sandbox lokal

Setelah stack di-migrate dan di-seed, alur sandbox dapat dicoba melalui
`http://localhost:8080`:

1. Masuk sebagai klien, ajukan booking ke Studio Cahaya, lalu keluar.
2. Masuk sebagai kreator, buka **Booking masuk**, terima booking, lalu keluar.
3. Masuk kembali sebagai klien, buka **Booking saya** → **Bayar sekarang**,
   buat pembayaran, lalu pilih **Simulasikan pembayaran berhasil**.
4. Untuk alur pencairan, masuk sebagai kreator, tandai booking selesai, buka
   halaman pembayarannya, lalu pilih **Simulasikan pencairan**.
5. Untuk alur refund, klien dapat membatalkan booking yang dananya masih
   berstatus held.

Status held (**Dana tercatat aman**) dan released (**Pembayaran telah dilepas**)
hanya state bisnis yang disimulasikan. Jepret belum menahan, memindahkan, atau
mencairkan dana nyata.

## Troubleshooting

- **Port 8080 terpakai** — hentikan proses lain atau ubah mapping `gateway.ports` di `docker-compose.yml`.
- **`/ready` mengembalikan 503** — database belum siap; cek `docker compose ps` dan `docker compose logs db`.
- **Migration gagal** — pastikan service `db` sehat lalu ulangi `docker compose run --rm migrate`.
- **Build web gagal di Docker** — pastikan `package-lock.json` ada dan sinkron (`npm install` di root).
- **Test integration Postgres deselected** — memang default; jalankan dengan `-m integration` setelah database tersedia.

## Security caveats

Kredensial default (`minioadmin`, `jepret`, dan akun demo) hanya untuk lokal.
Auth saat ini memakai password hash dan session cookie HttpOnly, SameSite=Lax
(Secure di production), ditambah pemeriksaan Origin untuk request mutasi.
Belum tersedia MFA, verifikasi email, password recovery, atau rate limiting.

Payment masih memakai mock provider tanpa dana nyata dan tanpa verifikasi
signature provider production. Mock webhook dan `/api/v1/dev/payments/*`
ditolak saat `JEPRET_ENVIRONMENT=production`; frontend simulasi juga tidak
dibangun oleh konfigurasi production. Jangan mengekspos stack Compose lokal ke
jaringan publik atau memakai mock provider untuk transaksi nyata.

## Deployment notes

Production deployment belum menjadi bagian Phase 1–5. Sebelum production,
siapkan secret terkelola, HTTPS, rate limiting, observability, backup, dan
provider payment nyata dengan webhook terautentikasi. Kebutuhan selengkapnya
didokumentasikan di `docs/deployment.md`.
