# Jepret Phase 4 — Booking Design

**Tanggal:** 2026-07-21 · **Status:** Approved (default rekomendasi, disetujui Bray)

## Ringkasan

Klien mengajukan booking ke kreator terverifikasi untuk tanggal tertentu.
Kreator menerima atau menolak. Kedua pihak dapat membatalkan selama belum
selesai; kreator menandai selesai setelah pekerjaan tuntas. Belum ada
pembayaran (Phase 5) dan chat (Phase 6).

## Keputusan desain

1. **Ketersediaan** — tanpa kalender. Klien mengisi `event_date` bebas
   (harus di masa depan). Bentrok dicegah saat kreator **menerima**: jika
   kreator sudah punya booking `accepted` di tanggal itu → 409
   `DATE_UNAVAILABLE`. Request boleh menumpuk; hanya satu yang bisa diterima.
2. **Status** — `requested → accepted | rejected`, lalu
   `accepted → completed | cancelled`. `requested → cancelled` juga sah.
   Status terminal: `rejected`, `completed`, `cancelled`.
3. **Pembatalan** — klien maupun kreator boleh membatalkan booking berstatus
   `requested` atau `accepted`. Kebijakan denda/refund menyusul Phase 5.

## Skema (migration `20260721_0004`)

Tabel `bookings`:

| Kolom | Tipe | Catatan |
| --- | --- | --- |
| `id` | UUID PK | |
| `client_id` | UUID FK users ON DELETE CASCADE | pemesan |
| `creator_profile_id` | UUID FK creator_profiles ON DELETE CASCADE | |
| `event_date` | DATE | tanggal acara |
| `event_city` | VARCHAR(100) | |
| `notes` | TEXT default `''` | ≤2000 char |
| `status` | VARCHAR(20) | CHECK in requested/accepted/rejected/completed/cancelled |
| `quoted_price_idr` | BIGINT | snapshot `starting_price_idr` saat request |
| `responded_at`, `completed_at`, `cancelled_at` | TIMESTAMPTZ NULL | |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

Index: `ix_bookings_client (client_id, created_at DESC)`,
`ix_bookings_creator (creator_profile_id, created_at DESC)`,
partial unique `uq_bookings_accepted_date (creator_profile_id, event_date)
WHERE status = 'accepted'` — bentrok tanggal dijamin di level database.

## API

Prefix `/api/v1/bookings`, semua butuh sesi.

| Method | Path | Aktor | Aksi |
| --- | --- | --- | --- |
| POST | `/bookings` | klien | buat request (body: `creator_id`, `event_date`, `event_city`, `notes`) → 201 |
| GET | `/bookings` | klien | daftar booking miliknya (terbaru dulu) |
| GET | `/bookings/incoming` | kreator | booking masuk ke profil kreatornya |
| GET | `/bookings/{id}` | pihak terkait | detail |
| POST | `/bookings/{id}/accept` | kreator | `requested → accepted` |
| POST | `/bookings/{id}/reject` | kreator | `requested → rejected` |
| POST | `/bookings/{id}/complete` | kreator | `accepted → completed` |
| POST | `/bookings/{id}/cancel` | klien atau kreator | `requested\|accepted → cancelled` |

`BookingOut`: `id`, `status`, `event_date`, `event_city`, `notes`,
`quoted_price_idr`, `created_at`, `creator` (id + display_name + city +
specialty), `client` (nama saja, hanya untuk kreator).

Error:
- Kreator tidak approved / tidak ada → 404 `NOT_FOUND`.
- `event_date` bukan masa depan → 422 `INVALID_EVENT_DATE`.
- Memesan diri sendiri → 422 `CANNOT_BOOK_SELF`.
- Bukan pihak terkait → 404 `NOT_FOUND` (tidak membocorkan keberadaan booking).
- Aksi oleh peran salah → 403 `FORBIDDEN`.
- Transisi status tidak sah → 409 `INVALID_STATUS_TRANSITION`.
- Tanggal sudah terisi saat accept → 409 `DATE_UNAVAILABLE`.

Semua transisi memakai `SELECT ... FOR UPDATE` pada baris booking.

## Frontend

- **`/kreator/[id]`** — CTA "Hubungi kreator" diganti **"Ajukan booking"**;
  jika belum login → arahkan `/masuk`. Form (tanggal, kota, catatan) di
  `/kreator/[id]/booking`, sukses → `/booking`.
- **`/booking`** — daftar booking klien: kartu status berwarna, tanggal, kreator,
  harga, tombol "Batalkan" bila belum terminal. Empty state mengarah ke beranda.
- **`/booking/masuk`** — untuk kreator approved: daftar request masuk dengan
  tombol Terima/Tolak, dan Tandai selesai untuk yang accepted.
- **Bottom nav** — item "Booking" jadi `Link` ke `/booking`.

Label status Indonesia: Menunggu konfirmasi, Diterima, Ditolak, Selesai, Dibatalkan.

## Seed

Tambah 3 booking demo dari `klien@jepret.local` ke Studio Cahaya:
satu `requested`, satu `accepted`, satu `completed` (tanggal berbeda), idempoten
berdasarkan pasangan (client, creator, event_date).

## Testing

- **Integration**: buat booking sukses; kreator non-approved 404; tanggal lampau
  422; booking diri sendiri 422; daftar klien vs kreator terpisah; orang lain
  akses detail 404; accept/reject/complete/cancel + transisi ilegal 409;
  dua accept pada tanggal sama 409 `DATE_UNAVAILABLE`; klien tidak boleh accept 403.
- **Vitest**: form booking (validasi + submit), daftar booking klien, daftar masuk kreator.
- **E2E**: klien login → detail kreator → ajukan booking → tampil di `/booking`;
  kreator login → `/booking/masuk` → terima → status berubah di kedua sisi.

## Di luar scope

Pembayaran/DP (Phase 5), chat (Phase 6), review (Phase 7), notifikasi email,
kalender ketersediaan, reschedule.
