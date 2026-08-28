# Progress Implementasi Jepret

- [x] Phase 0 — Discovery dan design approval
- [x] Phase 1 — Foundation
  - [x] Governance dan workspace
  - [x] API system foundation
  - [x] Database dan migration baseline
  - [x] Generated contracts
  - [x] Mobile-first web shell
  - [x] Local Docker stack
  - [x] CI dan final verification

  **Bukti verifikasi (2026-07-17, mesin lokal Windows):**

  - `npm run verify` hijau penuh: ruff format check, prettier check, ruff lint,
    ESLint (0 warning), mypy strict, tsc, pytest (6 passed, 1 deselected),
    Vitest (2 passed), contracts check (tanpa diff), Next.js build, compose config.
  - Integration test PostgreSQL: 1 passed (via debug port 15432).
  - E2E Playwright mobile-chromium: 2 passed (shell + health same-origin, WebSocket upgrade).
  - Stack Compose sehat: gateway, web, api, db, minio; migration baseline `20260713_0001` sukses.
  - Homepage, `/health`, `/ready` terverifikasi melalui gateway `http://localhost:8080`.

- [x] Phase 2 — Auth dan profiles

  **Bukti verifikasi (2026-07-20, mesin lokal Windows):**

  - pytest integration: 17 passed (auth, profiles, admin approval, schema, permission tests).
  - E2E Playwright mobile-chromium: 4 passed (foundation + daftar→keluar→masuk→onboarding
    kreator→ajukan verifikasi + pesan kredensial salah).
  - Migration `20260717_0002` (users, sessions, creator_profiles) dan seed 3 akun demo sukses.
  - Kontrak ter-regenerate dengan 10 route baru; `npm run verify` hijau.

- [x] Phase 3 — Marketplace

  **Bukti verifikasi (2026-07-21, mesin lokal Windows):**

  - pytest integration: 22 passed (termasuk listing approved-only, filter q/kota/
    spesialisasi/harga, paginasi cursor tanpa duplikat, validasi param, detail 404).
  - E2E Playwright mobile-chromium: 6 passed (pencarian → detail Studio Cahaya,
    filter tanpa hasil → empty state, + regresi foundation & auth).
  - Migration `20260721_0003` (index listing) dan seed 8 kreator approved idempoten.
  - Beranda live dengan cursor "Muat lebih"; detail `/kreator/[id]`;
    kartu link ber-aria-label (fix accessible name Chromium).

- [x] Phase 4 — Booking

  **Bukti verifikasi (2026-07-21, mesin lokal Windows):** lihat commit
  Phase 4 — migration `20260721_0004` (tabel bookings + partial unique
  accepted-date), 8 endpoint booking, halaman klien & kreator, seed 3 booking
  demo, E2E alur ajukan → terima.

- [x] Phase 5 — Payment

  **Bukti verifikasi (2026-08-02, mesin lokal Windows):**

  - Mock payment provider: 27 passed; booking/payment integration: 34 passed
    dengan 1 warning deprecation upstream Starlette/httpx.
  - Vitest web: 68 passed pada 12 test files.
  - E2E Playwright mobile-chromium: 8 passed (foundation, auth, marketplace,
    booking, payment), termasuk paid → held → completed → released dan paid →
    cancelled → refunded; focused payment flow 2 passed pada run berulang.
  - Stack Compose dibangun ulang dan sehat; migration head `20260731_0005`
    serta seed payment idempoten berhasil dijalankan.
  - `npm run verify` hijau penuh: format check, lint, mypy (30 source files),
    tsc, pytest (42 passed, 58 deselected), Vitest (68 passed), contracts check
    tanpa diff, Next.js build, dan Compose config.
  - Remediasi quality review diverifikasi ulang pada 2026-08-13: API sekarang
    mewajibkan environment eksplisit dan CI mengisi `JEPRET_ENVIRONMENT=test`;
    kreator dapat membuka **Lihat pembayaran** dari booking `confirmed` maupun
    `completed`. Focused config/provider pytest lulus 30 test; integration
    booking/payment lulus 34 test dengan 1 warning deprecation upstream
    Starlette/httpx; Vitest lulus 12 test files/69 test. Focused booking E2E
    lulus dua kali berturut-turut, masing-masing 3 test tanpa collision tak
    terduga, dan full Playwright lulus 9 test. `npm run verify` final lulus:
    Ruff format 55
    files, Ruff/ESLint, mypy 30 source files, tsc, pytest 44 passed/58
    deselected dengan 1 warning upstream, Vitest 12 files/69 test, contracts
    tanpa diff, Next.js build, dan Compose config.

- [x] Phase 6 — Chat dan deliverables

  **Bukti verifikasi (2026-08-28, mesin lokal Windows):**

  - Migration `20260816_0006` (tabel `conversations`, `messages`, `uploads`,
    `deliverables`, serta kolom timestamp booking `session_started_at`,
    `delivered_at`, `completed_at`).
  - Storage adapter MinIO: upload intent bertanda tangan (pre-signed PUT create-only
    dengan `If-None-Match: *`), MIME magic bytes validation server-side, dan
    download authorization berbatas waktu (pre-signed GET).
  - In-process real-time broadcast hub: koneksi WebSocket terautentikasi (`/ws/conversations/{id}`)
    dengan auto-reconnect backoff dan fallback keyset cursor polling pada client.
  - Lifecycle workspace: alur status `confirmed` → `in_progress` → `delivered` → `completed`
    dengan pelepasan pembayaran otomatis (`released`) terverifikasi.
  - Komponen workspace frontend: `WorkspaceHeader`, `UploadField`, `ConversationPanel`,
    `DeliverablesPanel`, dan halaman `/booking/[id]`.
  - Backend unit & integration test: pytest 99 passed (storage adapter, rate limiter,
    schema, bookings, payments, uploads, conversations, deliverables, lifecycle).
  - Frontend component test: Vitest 15 test files / 129 passed.
  - OpenAPI contracts check: 0 diff pada `openapi.json` & `schema.d.ts`.
  - `npm run verify` hijau penuh (formatcheck, lint, typecheck mypy 41 files & tsc,
    test pytest 99 + vitest 129, contracts check, Next.js build).

- [ ] Phase 7 — Completion, reviews, disputes, admin
- [ ] Phase 8 — Hardening
