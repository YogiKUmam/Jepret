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

## Komponen

- **Caddy (gateway)** — entry point tunggal `:8080`, kompresi, routing same-origin.
- **Next.js (web)** — PWA shell mobile-first, output standalone, TanStack Query boundary.
- **FastAPI (api)** — modular monolith; system routes (`/health`, `/ready`, `/ws/health`), error envelope stabil, correlation ID, structured logging.
- **PostgreSQL** — source of truth; akses async via SQLAlchemy + asyncpg; schema dikelola Alembic.
- **MinIO** — object storage lokal dengan bucket `jepret-public` dan `jepret-private`.
- **Redis** — profile Compose opsional; tidak diperlukan stack dasar.

## Request flow

1. Browser memanggil `http://localhost:8080/...` (satu origin untuk web, REST, dan WebSocket).
2. Caddy meneruskan `/health`, `/ready`, `/api/v1/*`, `/api/docs*`, `/api/openapi.json`, dan `/ws/*` ke FastAPI; sisanya ke Next.js.
3. `CorrelationIdMiddleware` membaca atau membuat `X-Request-ID` dan mengembalikannya pada response.
4. Error API selalu memakai envelope `{"error": {"code", "message", "details"}}`; sukses memakai `{"data": ...}`.

## Auth flow (Phase 2 — implemented)

Authentication berbasis session cookie same-origin tanpa CORS. Password di-hash Argon2id (pwdlib); session opaque token disimpan sebagai hash SHA-256 di tabel `sessions` dengan umur 30 hari. Cookie `jepret_session` bersifat HttpOnly + SameSite=Lax (+Secure di production). Endpoint: `/api/v1/auth/{register,login,logout,me}`, `/api/v1/profiles/*`, `/api/v1/admin/creator-applications*`. Proteksi CSRF: SameSite=Lax dikombinasikan `OriginCheckMiddleware` yang menolak method mutasi dengan header Origin asing (`FORBIDDEN_ORIGIN`). Satu akun dapat mengaktifkan profil kreator (status draft → pending → approved/rejected, approval oleh admin).

## Planned storage flow (fase fitur)

Upload media memakai bucket privat dengan signed URL berbatas waktu yang diterbitkan API setelah authorization. Bucket publik hanya untuk aset non-sensitif. Tidak ada direct public read terhadap bucket privat.

## WebSocket flow

`/ws/health` adalah probe infrastruktur untuk memvalidasi penerusan upgrade WebSocket oleh gateway. Business WebSocket terautentikasi (chat) ditambahkan pada Phase 6 melalui prefix `/ws/*` yang sama.

## ADR-001: Same-origin Caddy gateway

**Status:** Accepted

Caddy menjadi entry point tunggal agar cookie, CSRF, REST, dan WebSocket memiliki perilaku origin yang konsisten. PostgreSQL dan MinIO tetap internal; direct debug port memakai compose override eksplisit.
