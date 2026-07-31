# Jepret Phase 5 — Payment Design

**Tanggal:** 2026-07-31 · **Status:** Approved

## Ringkasan

Phase 5 menambahkan pembayaran penuh berbasis adapter ke booking yang sudah
diterima kreator. Implementasi pertama memakai `MockPaymentProvider` agar alur
lengkap dapat dijalankan secara lokal tanpa memegang dana nyata. Status `held`
dan `released` hanya merepresentasikan state bisnis sandbox, bukan escrow atau
split payment legal.

Klien membayar seluruh `quoted_price_idr`. Jepret mencatat biaya platform
simulasi 10% dari harga booking dan nilai bersih kreator sebagai data pembukuan.
Biaya tersebut tidak ditambahkan ke total yang dibayar klien.

## Scope

Phase ini mencakup:

- payment adapter dan mock provider;
- payment penuh untuk satu booking;
- pencatatan biaya platform simulasi 10%;
- pembuatan payment yang idempoten;
- webhook/event handling yang idempoten;
- simulasi payment berhasil dan release khusus development/test;
- refund penuh ketika booking berbayar dibatalkan sebelum selesai;
- state booking `awaiting_payment` dan `confirmed`;
- halaman pembayaran mobile-first;
- authorization, transaksi, tests, seed, kontrak, dan dokumentasi.

Di luar scope:

- provider produksi seperti Midtrans atau Xendit;
- pembayaran DP atau cicilan;
- biaya tambahan untuk klien;
- split payment atau escrow nyata;
- partial refund, denda pembatalan, chargeback, dan dispute;
- expiry berbasis background worker;
- payment untuk subscription atau featured listing.

## Pendekatan

Payment dipertahankan sebagai domain di modular monolith. Route handler tetap
tipis, sedangkan transaksi dan state machine berada di payment service.
`PaymentProvider` menjadi boundary untuk integrasi eksternal.
`MockPaymentProvider` mengimplementasikan kontrak yang sama dengan provider masa
depan, tetapi tidak melakukan network request.

Pendekatan ini dipilih dibanding mengubah status langsung dari route karena
adapter dan event handler memberi jalur migrasi yang jelas ke provider nyata.
Outbox atau event bus tidak digunakan karena belum diperlukan untuk MVP lokal.

## State machine

### Booking

Transisi yang relevan setelah Phase 5:

| Dari | Aksi | Ke |
| --- | --- | --- |
| `requested` | kreator menerima | `accepted` |
| `requested` | kreator menolak | `rejected` |
| `requested` | pihak terkait membatalkan | `cancelled` |
| `accepted` | klien membuat payment | `awaiting_payment` |
| `accepted` | pihak terkait membatalkan | `cancelled` |
| `awaiting_payment` | payment berhasil dan held | `confirmed` |
| `awaiting_payment` | pihak terkait membatalkan | `cancelled` |
| `confirmed` | kreator menandai selesai | `completed` |
| `confirmed` | pihak terkait membatalkan sebelum selesai | `cancelled` |

`rejected`, `completed`, dan `cancelled` tetap terminal. Phase 6 dapat
menambahkan `in_progress` dan `delivered` di antara `confirmed` dan `completed`
tanpa mengubah payment adapter.

### Payment

| Dari | Aksi | Ke |
| --- | --- | --- |
| tidak ada | klien membuat payment | `pending` |
| `pending` | provider melaporkan pembayaran berhasil | `held` |
| `pending` | booking dibatalkan | `expired` |
| `pending` | provider gagal | `failed` |
| `held` | booking dibatalkan sebelum selesai | `refunded` |
| `held` | release setelah booking selesai | `released` |

`released`, `refunded`, `failed`, dan `expired` adalah terminal. Kolom
`paid_at` dan `held_at` diisi bersamaan pada mock provider. Status `paid` tetap
diizinkan di constraint agar provider masa depan dapat mempunyai tahap
settlement terpisah, tetapi mock flow bergerak atomik dari `pending` ke `held`.

### Cancellation

- Booking `requested` atau `accepted` dibatalkan tanpa operasi payment.
- Booking `awaiting_payment` membatalkan booking dan mengubah payment `pending`
  menjadi `expired` dalam satu transaksi.
- Booking `confirmed` menjalankan refund penuh dan mengubah payment menjadi
  `refunded` serta booking menjadi `cancelled` dalam satu transaksi.
- Booking `completed` tidak dapat dibatalkan.
- Phase ini tidak mempunyai partial refund atau denda.

## Model data

Migration `20260731_0005`:

1. Memperbarui check constraint status booking untuk menerima
   `awaiting_payment` dan `confirmed`.
2. Mengganti partial unique index jadwal agar mencakup status `accepted`,
   `awaiting_payment`, dan `confirmed`. Dengan demikian, perubahan status saat
   payment dibuat atau berhasil tidak melepaskan perlindungan double booking.
3. Membuat tabel `payments`:

| Kolom | Tipe | Aturan |
| --- | --- | --- |
| `id` | UUID PK | generated |
| `booking_id` | UUID FK bookings | unique, ON DELETE CASCADE |
| `provider` | VARCHAR(20) | `mock` untuk Phase 5 |
| `provider_reference` | VARCHAR(100) | unique, nullable sebelum dibuat |
| `idempotency_key` | VARCHAR(100) | unique global, tidak diekspos |
| `amount_idr` | BIGINT | positif |
| `platform_fee_idr` | BIGINT | non-negatif |
| `creator_net_idr` | BIGINT | non-negatif |
| `status` | VARCHAR(20) | check state payment |
| `paid_at` | TIMESTAMPTZ | nullable |
| `held_at` | TIMESTAMPTZ | nullable |
| `released_at` | TIMESTAMPTZ | nullable |
| `refunded_at` | TIMESTAMPTZ | nullable |
| `raw_metadata` | JSONB | nullable, internal-only |
| `created_at`, `updated_at` | TIMESTAMPTZ | UTC |

Database check memastikan
`amount_idr = platform_fee_idr + creator_net_idr`.
Biaya dihitung dengan integer arithmetic:

```text
platform_fee_idr = amount_idr * 10 // 100
creator_net_idr = amount_idr - platform_fee_idr
```

4. Membuat tabel `payment_events`:

| Kolom | Tipe | Aturan |
| --- | --- | --- |
| `id` | UUID PK | generated |
| `payment_id` | UUID FK payments | ON DELETE CASCADE |
| `provider` | VARCHAR(20) | |
| `provider_event_id` | VARCHAR(150) | unique bersama provider |
| `event_type` | VARCHAR(50) | |
| `processed_at` | TIMESTAMPTZ | UTC |

Unique constraint `(provider, provider_event_id)` menjadi pengaman utama replay
webhook. Metadata mentah tersimpan hanya jika sudah disanitasi dan tidak pernah
dikembalikan oleh public API.

## Provider boundary

`PaymentProvider` menyediakan operasi:

```text
create_payment(payment) -> provider reference
get_payment_status(payment) -> provider status
handle_webhook(payload, headers) -> normalized payment event
refund_payment(payment) -> normalized payment event
release_payment(payment) -> normalized payment event
```

Provider tidak mengubah model database. Provider mengembalikan hasil
ternormalisasi, lalu payment service memvalidasi transisi dan menyimpan seluruh
perubahan dalam transaksi.

`MockPaymentProvider`:

- menghasilkan provider reference deterministik dari payment ID;
- tidak melakukan network request;
- menghasilkan event ID unik untuk aksi baru;
- dapat mengembalikan event yang sama untuk menguji replay;
- tidak diaktifkan sebagai provider publik di production.

## Transaction dan idempotency

Semua aksi perubahan payment mengunci baris booking dan payment yang terkait
dengan `SELECT ... FOR UPDATE`.

Pembuatan payment:

1. Kunci booking.
2. Pastikan aktor adalah klien pemilik dan status booking `accepted`.
3. Jika payment booking sudah ada dengan idempotency key yang sama, kembalikan
   payment tersebut.
4. Jika key sudah dipakai untuk request berbeda, kembalikan
   `IDEMPOTENCY_CONFLICT`.
5. Buat payment dan ubah booking ke `awaiting_payment` dalam satu transaksi.
6. Unique constraint `booking_id` menangani request bersamaan yang lolos sebelum
   salah satu commit.

Event provider:

1. Normalisasi dan validasi event melalui adapter.
2. Kunci payment dan booking.
3. Jika `(provider, provider_event_id)` sudah ada, kembalikan state saat ini
   tanpa side effect.
4. Validasi transisi payment dan booking.
5. Simpan event, payment, dan booking dalam satu transaksi.

Refund dan release memakai mekanisme event yang sama. Kegagalan adapter sebelum
commit tidak meninggalkan perubahan parsial.

## API

Semua response payment publik hanya memuat:

`id`, `booking_id`, `provider`, `amount_idr`, `platform_fee_idr`,
`creator_net_idr`, `status`, timestamp status, dan `created_at`.
`raw_metadata`, idempotency key, serta payload provider tidak pernah diekspos.

| Method | Path | Aktor | Perilaku |
| --- | --- | --- | --- |
| POST | `/api/v1/bookings/{id}/payments` | klien pemilik | Membuat atau mengembalikan payment booking |
| GET | `/api/v1/bookings/{id}/payments` | pihak terkait | Ringkasan payment tanpa metadata internal |
| POST | `/api/v1/payments/webhooks/{provider}` | provider | Memproses event tervalidasi dan idempoten |
| POST | `/api/v1/dev/payments/{id}/simulate-paid` | klien pemilik | Development/test saja; menghasilkan event held |
| POST | `/api/v1/dev/payments/{id}/simulate-release` | kreator terkait | Development/test saja; hanya setelah completed |

`POST /bookings/{id}/payments` menerima header `Idempotency-Key`. Frontend
menghasilkan satu UUID dan mempertahankannya untuk retry selama sesi pembayaran.
Jika payment untuk booking sudah ada tetapi key awal tidak lagi tersedia,
service tetap mengembalikan payment yang sama kepada klien pemilik karena
booking hanya boleh mempunyai satu payment.

Webhook mendelegasikan validasi signature kepada adapter. Provider yang tidak
dikenal menghasilkan 404. Mock webhook hanya aktif di development/test.

## Authorization

- Hanya klien pemilik booking dapat membuat payment dan menjalankan simulasi
  pembayaran.
- Klien dan kreator yang terkait booking dapat membaca ringkasan payment.
- Hanya kreator terkait dapat menjalankan simulasi release, dan hanya setelah
  booking `completed`.
- Pengguna yang tidak terkait menerima 404 agar keberadaan booking/payment tidak
  bocor.
- Dev endpoints menghasilkan 404 `DEV_ENDPOINT_DISABLED` di production.
- Authorization selalu dilakukan di backend.

## Frontend

### Daftar booking klien

`/booking` menambahkan:

- tombol **Bayar sekarang** untuk status `accepted`;
- label **Menunggu pembayaran** untuk `awaiting_payment`;
- label **Terkonfirmasi** untuk `confirmed`;
- status payment ringkas untuk booking yang sudah mempunyai payment;
- tautan ke halaman pembayaran.

### Halaman pembayaran

Halaman `/booking/[id]/pembayaran` menampilkan:

- identitas kreator, tanggal dan kota acara;
- total yang dibayar klien;
- penjelasan bahwa provider adalah simulasi sandbox;
- tombol **Buat pembayaran** ketika booking `accepted`;
- tombol **Simulasikan pembayaran berhasil** ketika payment `pending`;
- status sukses ketika payment `held`;
- status final untuk `refunded`, `released`, `failed`, atau `expired`;
- tombol **Simulasikan pencairan** hanya pada development/test, untuk kreator
  terkait setelah booking `completed`.

UI tidak menambahkan biaya 10% ke total klien. Rincian biaya platform dan nilai
bersih kreator ditampilkan kepada kreator pada ringkasan pembayaran.

Seluruh tampilan mobile-first, dapat digunakan dengan keyboard, mempunyai label
aksesibel, dan menangani loading, empty, error, dan success state.

### Daftar booking kreator

`/booking/masuk` memperbarui label dan aksi:

- `accepted`: menunggu klien membuat pembayaran;
- `awaiting_payment`: menunggu pembayaran berhasil;
- `confirmed`: booking terkonfirmasi dan dapat ditandai selesai;
- `completed` dengan payment `held`: pada development/test tersedia tautan untuk
  simulasi release.

## Error contract

| Status | Code | Kondisi |
| --- | --- | --- |
| 404 | `NOT_FOUND` | Booking/payment tidak ada atau aktor tidak terkait |
| 404 | `DEV_ENDPOINT_DISABLED` | Dev endpoint dipanggil di production |
| 409 | `PAYMENT_NOT_ALLOWED` | Status booking tidak mengizinkan pembuatan payment |
| 409 | `PAYMENT_ALREADY_FINAL` | Aksi diminta pada payment terminal |
| 409 | `INVALID_PAYMENT_TRANSITION` | Event tidak valid untuk state saat ini |
| 409 | `IDEMPOTENCY_CONFLICT` | Key sama dipakai untuk request berbeda |
| 422 | `INVALID_IDEMPOTENCY_KEY` | Header hilang atau format tidak valid |

Replay event yang sama bukan error dan mengembalikan state saat ini. Error
provider tidak mengekspos payload, signature, atau detail internal.

## Seed

Seed lokal menambahkan payment untuk booking demo tanpa menggandakan data:

- satu payment `pending` pada booking `awaiting_payment`;
- satu payment `held` pada booking `confirmed`;
- satu payment `released` pada booking `completed`.

Seed menggunakan booking/provider reference sebagai natural idempotency
boundary dan tetap aman dijalankan berulang.

## Testing

### Backend

- Migration upgrade dan downgrade menjaga constraint booking/payment.
- Perhitungan fee memakai integer dan selalu menjaga invariant total.
- Hanya klien pemilik dapat membuat payment.
- Kreator dan klien terkait dapat membaca ringkasan; orang lain mendapat 404.
- Payment hanya dapat dibuat dari booking `accepted`.
- Retry dengan key sama mengembalikan payment yang sama.
- Key sama untuk booking berbeda menghasilkan `IDEMPOTENCY_CONFLICT`.
- Dua request bersamaan menghasilkan satu payment.
- Event paid mengubah payment ke `held` dan booking ke `confirmed` secara atomik.
- Replay event tidak menghasilkan perubahan kedua.
- Pembatalan `awaiting_payment` menghasilkan `expired`.
- Pembatalan `confirmed` menghasilkan refund penuh.
- Kegagalan refund membatalkan seluruh transaksi.
- Release ditolak sebelum booking selesai dan berhasil sesudah selesai.
- Dev endpoints tidak terdaftar/tersedia pada production.
- Metadata internal tidak muncul dalam response.

### Frontend

- Booking `accepted` menampilkan CTA pembayaran.
- Halaman payment membuat payment dengan idempotency key stabil pada retry.
- Simulasi paid memperbarui status menjadi terkonfirmasi.
- Loading, error, terminal, dan retry state tampil benar.
- Ringkasan kreator menampilkan fee dan nilai bersih tanpa mengubah total klien.

### E2E

Alur utama:

1. Kreator menerima booking.
2. Klien membuka halaman pembayaran.
3. Klien membuat payment dan mensimulasikan pembayaran berhasil.
4. Booking tampil terkonfirmasi pada kedua akun.
5. Kreator menandai booking selesai.
6. Kreator menjalankan simulasi release.
7. Payment tampil released.

Alur pembatalan menguji booking confirmed menjadi cancelled dan payment held
menjadi refunded.

## Dokumentasi dan operasional

- OpenAPI dan TypeScript contracts digenerate ulang.
- README diperbarui agar status fase, akun demo, dan instruksi sandbox sesuai
  implementasi aktual.
- `docs/implementation-plan.md` baru menandai Phase 5 selesai setelah seluruh
  quality gate dan E2E lulus.
- Tidak ada secret provider dalam repository.
- Environment menentukan apakah dev payment endpoints tersedia.

## Kriteria selesai

Phase 5 selesai ketika payment sandbox dapat dibuat, dibayar, dibatalkan dengan
refund, dan dilepas secara end-to-end; transaksi serta idempotency teruji;
authorization tests lulus; migration dan generated contracts sinkron; dan
`npm run verify` berhasil.
