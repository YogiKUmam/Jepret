# Jepret Phase 2 — Auth & Profiles Implementation Plan

> Design: `docs/superpowers/specs/2026-07-17-jepret-auth-profiles-design.md`
> Pola kerja sama dengan Phase 1: TDD per task (RED → GREEN), commit per task,
> `npm run verify` sebelum menyatakan selesai. Verifikasi runtime (Docker, E2E,
> integration) dijalankan di mesin Windows Bray; penulisan file oleh Claude.

**Goal:** Email+password auth berbasis session cookie, profil client, onboarding
kreator dengan approval admin, seed akun demo, halaman `/daftar`, `/masuk`,
`/profil`, `/profil/kreator`, kontrak ter-regenerate, CI tetap hijau.

---

### Task 1: Password hashing & session token utilities

**Files:** `apps/api/pyproject.toml` (tambah `pwdlib[argon2]`), `apps/api/app/core/security.py`, `apps/api/tests/test_security.py`

- [ ] Tambah dependency `pwdlib[argon2]` (range `>=0.2`), `uv lock` + `uv sync` di mesin Bray.
- [ ] RED: test hash≠plain, verify benar/salah, `generate_session_token()` unik ≥43 char, `hash_session_token()` deterministik SHA-256 hex.
- [ ] GREEN: implement `hash_password`, `verify_password` (pwdlib Argon2id), `generate_session_token` (`secrets.token_urlsafe(32)`), `hash_session_token`.
- [ ] Commit: `feat(api): add password and session token security utils`

### Task 2: Models & migration 0002

**Files:** `apps/api/app/db/models.py` (Base + User, Session, CreatorProfile), `apps/api/migrations/versions/20260717_0002_auth_profiles.py`, `apps/api/tests/integration/test_auth_schema.py`

- [ ] SQLAlchemy 2.0 typed models sesuai skema design doc; enum status via `VARCHAR` + CHECK constraint; semua timestamp `TIMESTAMPTZ` UTC.
- [ ] Migration 0002 (down_revision `20260713_0001`) membuat 3 tabel + index; `downgrade` drop urut.
- [ ] Integration test (marker `integration`): upgrade head lalu insert/select user via engine.
- [ ] Verifikasi mesin Bray: `docker compose run --rm migrate` + integration test via port 15432.
- [ ] Commit: `feat(api): add auth and creator profile schema`

### Task 3: Auth service (register, login, logout, current user)

**Files:** `apps/api/app/services/__init__.py`, `apps/api/app/services/auth.py`, `apps/api/app/api/deps.py`, `apps/api/tests/test_auth_service.py`

- [ ] Service murni ber-session AsyncSession: `register_user` (email lowercase, cek `EMAIL_TAKEN`, hash, auto-create session), `login` (`INVALID_CREDENTIALS` generik), `logout` (hapus session), `get_user_by_session_token` (cek expiry).
- [ ] Domain error class `DomainError(code, message, status)` dipetakan handler global ke envelope error Phase 1.
- [ ] `app/api/deps.py`: dependency `get_current_user` (baca cookie → service; 401 `UNAUTHENTICATED`) dan `require_admin` (403 `FORBIDDEN`).
- [ ] Unit test service pakai SQLite aiosqlite? TIDAK — tetap PostgreSQL-only sesuai stack: unit test service memakai fake repository TIDAK dipakai; gunakan TestClient + dependency override di Task 4, dan service test digabung integration ringan. Keputusan: test service via TestClient route-level (menghindari dobel infrastruktur).
- [ ] Commit: `feat(api): add auth domain service and dependencies`

### Task 4: Auth API routes + CSRF origin guard

**Files:** `apps/api/app/api/auth.py`, `apps/api/app/core/middleware.py` (OriginCheckMiddleware), `apps/api/app/main.py`, `apps/api/tests/test_auth_api.py`

- [ ] RED: register set cookie + 201; register email duplikat → 409 `EMAIL_TAKEN`; login benar → cookie; login salah → 401 `INVALID_CREDENTIALS`; `GET /auth/me` tanpa cookie → 401; dengan cookie → data user; logout menghapus cookie + session; POST dengan `Origin` asing → 403 `FORBIDDEN_ORIGIN`.
- [ ] Cookie helper: nama `jepret_session`, HttpOnly, SameSite=Lax, `secure=settings.environment is PRODUCTION`, max_age 30 hari.
- [ ] `OriginCheckMiddleware`: hanya method mutasi; izinkan Origin absen (curl/tools) atau sama dengan `public_origin`.
- [ ] Route prefix `/api/v1/auth`. Endpoint test via TestClient dengan dependency override `get_session` → session transaksi rollback (fixture `db_session`) — butuh PostgreSQL; tandai file ini `integration`? Keputusan: pakai marker `integration` untuk test yang menyentuh DB nyata; CI job quality sudah menyediakan PostgreSQL, tambahkan langkah migrate + jalankan `pytest -m integration` (sudah ada di workflow).
- [ ] Commit: `feat(api): add session cookie auth endpoints`

### Task 5: Profiles & creator onboarding + admin approval

**Files:** `apps/api/app/services/profiles.py`, `apps/api/app/api/profiles.py`, `apps/api/app/api/admin.py`, `apps/api/tests/test_profiles_api.py`, `apps/api/tests/test_admin_api.py`

- [ ] `PATCH /profiles/me`; `PUT /profiles/me/creator` (upsert draft; tolak edit saat `pending`); `POST /profiles/me/creator/submit` (validasi lengkap → `pending`, dalam transaksi); admin list/approve/reject (`reviewed_at`, transisi hanya dari `pending`, selain itu 409 `INVALID_STATUS_TRANSITION`).
- [ ] Permission tests wajib: non-login 401 semua; user biasa akses admin route → 403; user A tidak bisa memengaruhi profil user B; approve dari status `draft` → 409.
- [ ] Commit: `feat(api): add profile management and creator approval flow`

### Task 6: Seed demo accounts

**Files:** `apps/api/scripts/seed_demo.py`, `docker-compose.yml` (service `seed`, profile `tools`), `README.md` (bagian Akun demo)

- [ ] Script idempotent (upsert by email) membuat admin/klien/kreator sesuai design doc; kreator langsung `approved`.
- [ ] `docker compose run --rm seed` menjalankan `uv run --no-dev python scripts/seed_demo.py`.
- [ ] Update README Akun demo dengan tabel kredensial lokal + peringatan jangan dipakai production.
- [ ] Commit: `feat(api): seed local demo accounts`

### Task 7: Regenerate contracts

- [ ] Mesin Bray: `npm run contracts:generate` → commit `openapi.json` + `schema.d.ts` (LF via .gitattributes).
- [ ] `npm run contracts:check` bersih.
- [ ] Commit: `feat: regenerate contracts with auth and profile routes`

### Task 8: Frontend API client & auth hooks

**Files:** `apps/web/src/lib/api.ts`, `apps/web/src/lib/auth.ts` (`useMe`, `useLogin`, `useRegister`, `useLogout`), `apps/web/src/lib/api.test.ts`

- [ ] `apiFetch` generik: base `/api/v1`, `credentials: "same-origin"`, lempar `ApiError{code,message,status}` dari envelope; tipe respons dari `@jepret/contracts`.
- [ ] Hooks TanStack Query; `useMe` retry 0, treat 401 sebagai `null` (bukan error); mutasi meng-invalidate `["auth","me"]`.
- [ ] Vitest dengan `fetch` di-mock.
- [ ] Commit: `feat(web): add typed api client and auth hooks`

### Task 9: Halaman daftar & masuk

**Files:** `apps/web/src/app/(auth)/daftar/page.tsx`, `apps/web/src/app/(auth)/masuk/page.tsx`, komponen form bersama `apps/web/src/components/auth/*`, test `page.test.tsx` per halaman

- [ ] Form react-hook-form + zodResolver; label Indonesia; error `EMAIL_TAKEN`/`INVALID_CREDENTIALS` tampil manusiawi; disabled+spinner saat submit; sukses → redirect `/profil`.
- [ ] Test: validasi klien (email invalid, password <8), submit sukses memanggil mutasi.
- [ ] Commit: `feat(web): add register and login pages`

### Task 10: Halaman profil & onboarding kreator

**Files:** `apps/web/src/app/profil/page.tsx`, `apps/web/src/app/profil/kreator/page.tsx`, `apps/web/src/components/layout/bottom-navigation.tsx` (Profil → link), tests

- [ ] `/profil`: guard (redirect `/masuk` bila belum login), tampil nama/email, edit full_name, tombol logout, kartu status kreator (belum ada / draft / pending / approved / rejected + alasan CTA).
- [ ] `/profil/kreator`: form draft (display_name, city, specialty, starting_price_idr, bio), tombol "Ajukan verifikasi" saat draft lengkap; readonly saat pending/approved.
- [ ] Bottom nav: Profil jadi `<Link href="/profil">`; item lain tetap span.
- [ ] Commit: `feat(web): add profile and creator onboarding pages`

### Task 11: E2E auth flow

**Files:** `apps/web/e2e/auth.spec.ts`

- [ ] Skenario: register user baru (email random) → auto masuk → `/profil` menampilkan nama → logout → login ulang → isi draft kreator → submit → status "Menunggu verifikasi".
- [ ] Jalankan di mesin Bray dengan stack Compose + migrate + seed.
- [ ] Commit: `test: add auth and creator onboarding e2e`

### Task 12: Docs, verifikasi final, push

- [ ] Update `docs/architecture.md` (auth flow definitif), `docs/testing.md` (perintah baru: seed, e2e auth), `docs/implementation-plan.md` (Phase 2 + bukti), README (akun demo, endpoint auth).
- [ ] Mesin Bray: `npm run verify`, integration tests, E2E penuh, lalu `git push` dan pastikan CI hijau.
- [ ] Handoff report format AGENTS.md.
