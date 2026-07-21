# Jepret Phase 3 — Marketplace Design

**Tanggal:** 2026-07-21 · **Status:** Approved (keputusan bersama Bray)

## Ringkasan

Marketplace publik: daftar kreator ber-status `approved`, pencarian kata kunci,
filter kota/spesialisasi/harga, paginasi cursor, dan halaman detail kreator.
Tanpa upload media (placeholder gradient/inisial); tanpa rating (reviews di
Phase 7). Semua endpoint publik — tidak butuh sesi.

## Keputusan desain

1. **Pencarian** — filter + kata kunci sederhana: `ILIKE` PostgreSQL pada
   `display_name` dan `bio` (wildcard `%`/`_` di-escape). Full-text search
   ditunda sampai ada kebutuhan relevansi.
2. **Paginasi** — keyset/cursor, urutan `reviewed_at DESC, id DESC`
   (kreator yang baru di-approve tampil dulu; `id` sebagai tiebreak stabil).
   Cursor = base64url dari `"{reviewed_at_iso}|{id}"`, opaque bagi client.
   Ambil `limit + 1` baris untuk menentukan `next_cursor`.
3. **Media** — ditunda. Kartu & detail memakai blok gradient + inisial.
4. **URL detail** — `/kreator/[id]` dengan UUID `creator_profiles.id`.

## API

Prefix `/api/v1/creators`, publik (tanpa cookie), hanya profil `approved`.

| Method | Path | Query/Path | Response |
| --- | --- | --- | --- |
| GET | `/creators` | `q` (≤100), `city`, `specialty`, `min_price`, `max_price` (≥0), `cursor`, `limit` (1–50, default 12) | `{"data": {"items": [CreatorPublicOut], "next_cursor": str \| null}}` |
| GET | `/creators/{creator_id}` | UUID path | `{"data": CreatorPublicOut}` |

`CreatorPublicOut`: `id`, `display_name`, `city`, `specialty`,
`starting_price_idr`, `bio`.

Semantik filter:
- `q`: ILIKE `%q%` pada `display_name` OR `bio` (case-insensitive).
- `city`, `specialty`: cocok penuh case-insensitive (`LOWER(col) = LOWER(v)`).
- `min_price`/`max_price`: rentang inklusif pada `starting_price_idr`.

Error:
- Cursor tidak valid (bukan base64/format salah) → 422 `INVALID_CURSOR`.
- Detail bukan `approved` atau tidak ada → 404 `NOT_FOUND`
  (tidak membocorkan keberadaan profil pending/rejected).
- Query param salah bentuk → 422 `REQUEST_VALIDATION_FAILED` (handler Phase 1).

Index baru (migration `20260721_0003`):
`ix_creator_profiles_listing` pada `(status, reviewed_at DESC, id DESC)` untuk
jalur listing; kolom filter mengandalkan seq scan dulu (dataset kecil).

## Frontend

- **Beranda (`/`)** — kolom pencarian yang sudah ada di-wire ke listing;
  filter kota + spesialisasi (input teks) dan tombol "Terapkan". Grid
  `CreatorCard` (link ke `/kreator/[id]`), tombol **"Muat lebih"** saat
  `next_cursor` tersedia. `useInfiniteQuery` TanStack, key
  `["creators", filters]`.
- **Detail (`/kreator/[id]`)** — client component `useQuery`; gradient
  placeholder, badge TERVERIFIKASI, nama, kota · spesialisasi, bio,
  "Mulai Rp…", CTA "Hubungi kreator" (disabled, tooltip "Segera hadir" —
  booking Phase 4). 404 → pesan "Kreator tidak ditemukan".
- **Navigasi** — item "Jelajah" di bottom nav menjadi `Link` ke `/`.
- Kartu statis `CreatorPreviewCard` diganti data live (seed menyediakan
  Studio Cahaya + kreator demo lain).

## Seed

`seed_demo.py` diperluas: +7 kreator approved (kota & spesialisasi beragam:
Jakarta/Bandung/Yogyakarta/Surabaya/Bali; wedding/portrait/product/event/video),
password pola sama `*12345`, email `kreator2@jepret.local` dst. Idempoten
(upsert by email). `reviewed_at` dibuat berjenjang agar urutan listing
deterministik.

## Testing

- **Integration (pytest)**: hanya approved yang tampil; filter q/kota/
  spesialisasi/harga; kombinasi filter; paginasi cursor 2 halaman tanpa
  duplikat/celah; `INVALID_CURSOR` 422; detail approved 200, pending/absen 404.
- **Vitest**: CreatorCard render; halaman beranda memuat listing (fetch stub),
  "Muat lebih" menambah item; halaman detail render + state 404.
- **E2E (Playwright)**: cari "Studio" → hasil tampil → klik kartu → halaman
  detail Studio Cahaya; filter kota tanpa hasil → pesan kosong.

## Di luar scope Phase 3

Upload foto/galeri (MinIO signed URL), rating & reviews (Phase 7), slug URL,
full-text search, facet kota/spesialisasi dinamis, sorting pilihan user.
