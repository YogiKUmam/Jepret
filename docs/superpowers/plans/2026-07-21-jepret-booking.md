# Jepret Phase 4 — Booking Implementation Plan

> Design: `docs/superpowers/specs/2026-07-21-jepret-booking-design.md`

### Task 1: Model & migration 0004
`apps/api/app/db/models.py`, `migrations/versions/20260721_0004_bookings.py`
- Model `Booking` + relationship; partial unique index accepted-date.
- Commit: `feat(api): add booking schema`

### Task 2: Booking service
`apps/api/app/services/bookings.py`
- create_booking (validasi kreator approved, tanggal, self-book, snapshot harga),
  list_for_client, list_for_creator, get_for_user, accept/reject/complete/cancel
  dengan FOR UPDATE + guard transisi + DATE_UNAVAILABLE.
- Commit: `feat(api): add booking domain service`

### Task 3: Booking API + schemas
`apps/api/app/api/bookings.py`, `schemas.py`, `main.py`, `tests/test_bookings_api.py`
- 8 endpoint sesuai design; test integration lengkap (termasuk permission).
- Commit: `feat(api): add booking endpoints`

### Task 4: Seed booking demo
`apps/api/scripts/seed_demo.py`
- Commit: `feat(api): seed demo bookings`

### Task 5: Contracts regenerate (mesin Bray)

### Task 6: Frontend hooks
`apps/web/src/lib/bookings.ts` + test
- Commit: `feat(web): add booking hooks`

### Task 7: Form booking + halaman daftar klien
`/kreator/[id]/booking`, `/booking`, CTA di detail kreator, bottom nav
- Commit: `feat(web): client booking flow`

### Task 8: Halaman booking masuk kreator
`/booking/masuk`
- Commit: `feat(web): creator incoming bookings`

### Task 9: E2E + docs + verifikasi final + push
`e2e/booking.spec.ts`, docs, implementation-plan
- Commit: `docs: record booking phase completion`
