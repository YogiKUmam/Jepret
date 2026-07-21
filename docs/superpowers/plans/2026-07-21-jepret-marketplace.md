# Jepret Phase 3 — Marketplace Implementation Plan

> Design: `docs/superpowers/specs/2026-07-21-jepret-marketplace-design.md`
> Pola sama dengan Phase 2: TDD per task, commit per task, verifikasi runtime
> (integration, contracts, E2E) di mesin Windows Bray.

**Goal:** Listing kreator approved publik dengan pencarian + filter + cursor
pagination, halaman detail `/kreator/[id]`, beranda live, seed diperluas,
kontrak ter-regenerate, CI hijau.

---

### Task 1: Listing service (query publik + cursor)

**Files:** `apps/api/app/services/creators.py`, `apps/api/tests/test_creators_service.py` (marker integration)

- [ ] `encode_cursor(reviewed_at, id)` / `decode_cursor(str)` base64url; decode gagal → `DomainError("INVALID_CURSOR", 422)`.
- [ ] `list_creators(session, q, city, specialty, min_price, max_price, cursor, limit)` → `(items, next_cursor)`; hanya `status='approved'`; ILIKE escaped; keyset `(reviewed_at, id) < (c_r, c_i)`; ambil `limit+1`.
- [ ] `get_creator(session, creator_id)` → approved atau `DomainError("NOT_FOUND", 404)`.
- [ ] Commit: `feat(api): add public creator listing service`

### Task 2: Public API routes + index migration

**Files:** `apps/api/app/api/creators.py`, `apps/api/app/api/schemas.py` (CreatorPublicOut + envelope), `apps/api/migrations/versions/20260721_0003_creator_listing_index.py`, `apps/api/app/main.py`, `apps/api/tests/test_creators_api.py`

- [ ] RED: hanya approved tampil; filter q/city/specialty/harga; paginasi 2 halaman tanpa duplikat; limit di luar 1–50 → 422; cursor rusak → 422 `INVALID_CURSOR`; detail approved 200; pending/random UUID → 404.
- [ ] GREEN: router publik `/api/v1/creators` (tanpa dependency auth), migration index `(status, reviewed_at DESC, id DESC)`.
- [ ] Verifikasi mesin Bray: `docker compose build migrate && docker compose run --rm migrate` + pytest integration via 15432.
- [ ] Commit: `feat(api): add public creator marketplace endpoints`

### Task 3: Perluas seed demo

**Files:** `apps/api/scripts/seed_demo.py`

- [ ] +7 kreator approved (kota/spesialisasi/harga beragam, reviewed_at berjenjang), idempoten.
- [ ] Verifikasi mesin Bray: `docker compose build seed && docker compose run --rm seed` (2x, tanpa duplikat).
- [ ] Commit: `feat(api): seed marketplace demo creators`

### Task 4: Regenerate contracts (mesin Bray)

- [ ] `npm run contracts:generate` → commit `chore: regenerate contracts for marketplace routes`.

### Task 5: Frontend hooks & API types

**Files:** `apps/web/src/lib/api.ts` (CreatorPublic + list types), `apps/web/src/lib/creators.ts` (useCreatorsInfinite, useCreator), `apps/web/src/lib/creators.test.ts`

- [ ] `useCreatorsInfinite(filters)` via `useInfiniteQuery` (getNextPageParam = next_cursor); `useCreator(id)` (404 → null / error state).
- [ ] Commit: `feat(web): add marketplace query hooks`

### Task 6: Beranda live (search + filter + muat lebih)

**Files:** `apps/web/src/components/creators/creator-card.tsx`, `creator-list.tsx`, `apps/web/src/app/page.tsx`, `page.test.tsx`, hapus `creator-preview-card.tsx`, `bottom-navigation.tsx` (Jelajah → Link "/")

- [ ] Form pencarian ter-wire (submit set state filter), grid kartu link `/kreator/[id]`, tombol "Muat lebih", state kosong "Tidak ada kreator yang cocok.", skeleton loading.
- [ ] Vitest: render listing dari fetch stub, muat lebih menambah kartu, state kosong.
- [ ] Commit: `feat(web): live marketplace listing on home`

### Task 7: Halaman detail kreator

**Files:** `apps/web/src/app/kreator/[id]/page.tsx`, `page.test.tsx`

- [ ] Detail lengkap + badge TERVERIFIKASI + CTA "Hubungi kreator" disabled ("Segera hadir"); 404 → "Kreator tidak ditemukan" + link kembali.
- [ ] Commit: `feat(web): creator detail page`

### Task 8: E2E, docs, verifikasi final, push

**Files:** `apps/web/e2e/marketplace.spec.ts`, `docs/architecture.md`, `docs/implementation-plan.md`, `README.md`

- [ ] E2E: beranda memuat kreator seed → cari "Studio" → klik → detail Studio Cahaya; filter kota "Nonexist" → state kosong.
- [ ] Verifikasi mesin Bray: `npm run verify`, pytest integration penuh, stack rebuild + seed + E2E.
- [ ] Update docs + progress, push, CI hijau.
- [ ] Commit: `docs: record marketplace phase completion`
