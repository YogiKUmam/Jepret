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

- [ ] Phase 4 — Booking
- [ ] Phase 5 — Payment
- [ ] Phase 6 — Chat dan deliverables
- [ ] Phase 7 — Completion, reviews, disputes, admin
- [ ] Phase 8 — Hardening
