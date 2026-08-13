# Jepret Phase 5 Quality Remediation Design

**Tanggal:** 2026-08-13  
**Status:** Disetujui  
**Scope:** Menutup tiga temuan Important dan tiga temuan Minor dari quality review Phase 5 Task 9 tanpa mengubah payment state machine atau schema database.

## Latar belakang

Phase 5 Task 9 telah menyelesaikan payment E2E, dokumentasi sandbox, dan repository verification. Spec review menyatakan implementasi sesuai rencana, tetapi quality review menemukan tiga masalah yang menghalangi approval:

1. E2E memakai tanggal tetap sehingga retry atau rerun setelah proses terputus dapat berbenturan dengan booking aktif sebelumnya.
2. Kreator hanya dapat membuka payment page melalui URL yang disimpan dari sesi klien; alur tersebut tidak dapat dicapai dari UI kreator.
3. Backend menganggap environment yang tidak diberikan sebagai `development`, sehingga mock webhook dan development payment endpoints dapat aktif akibat salah konfigurasi deployment.

Review juga menemukan ketidakakuratan kecil pada wording production bundle, hubungan `.env.example` dengan Compose frontend build, dan locator list item di Playwright.

## Keputusan desain

Dipilih pendekatan fail-closed yang memperbaiki seluruh jalur pengguna dan bukti E2E, bukan hanya menyesuaikan dokumentasi atau menambah cleanup khusus test.

### 1. Environment backend wajib eksplisit

`Settings.environment` tidak memiliki default. Startup API harus gagal dengan validation error jika `JEPRET_ENVIRONMENT` hilang atau invalid.

- Local Compose menetapkan `JEPRET_ENVIRONMENT=development` secara eksplisit.
- Test dan tooling yang membuat `Settings` harus menetapkan environment secara eksplisit.
- Production deployment wajib menetapkan `JEPRET_ENVIRONMENT=production`.
- Mock webhook dan `/api/v1/dev/payments/*` tetap menolak production dengan 404.
- Tidak ada fallback yang mengaktifkan mock payment secara diam-diam.

Perubahan ini tidak mengubah authorization, payment provider contract, transaction boundary, idempotency, atau payment state machine.

### 2. Jalur payment kreator tersedia dari UI

Halaman **Booking masuk** menampilkan link **Lihat pembayaran** dengan route `/booking/{bookingId}/pembayaran` untuk:

- booking `confirmed` (**Terkonfirmasi**), berdampingan dengan aksi **Tandai selesai**;
- booking `completed` (**Selesai**), sebagai aksi utama yang tersedia.

Kreator dapat memantau state held sebelum menyelesaikan booking. Setelah booking selesai, kreator membuka route yang sama dan—hanya pada development/test serta payment held—dapat menjalankan **Simulasikan pencairan**.

Payment page tetap menjalankan authorization melalui API. Menampilkan link tidak memberikan akses baru kepada pengguna yang tidak berwenang.

### 3. E2E tahan retry dan rerun

Sebelum mengajukan booking, test masuk sebagai kreator dan membaca
`GET /api/v1/bookings/incoming` melalui browser request context yang sama. Test
kemudian memilih tanggal pertama mulai satu tahun dari hari eksekusi yang belum
digunakan oleh booking masuk mana pun. Setelah itu test keluar dan menjalankan
seluruh product flow melalui UI.

Setiap test attempt membuat:

- catatan booking unik;
- tanggal masa depan yang dipastikan kosong berdasarkan data booking kreator saat itu;
- locator semantik `getByRole("listitem")` yang difilter berdasarkan catatan dan status.

Pemilihan tanggal memindai kandidat berikutnya bila tanggal awal sudah dipakai,
sehingga retry, repeat, dan rerun setelah proses terputus tidak mengandalkan
cleanup ataupun probabilitas angka acak. Dua test yang berjalan pada worker
berbeda menggunakan offset awal berbeda; suite booking tetap berjalan serial
terhadap seed creator yang sama agar proses check-and-accept tidak berlomba.
Kedua skenario memakai identitas booking yang berbeda:

1. client request → creator accept → client pay → creator complete → creator click **Lihat pembayaran** → release;
2. client request → creator accept → client pay → client cancel → refund terlihat.

Test release tidak boleh menyimpan atau menggunakan URL dari sesi klien untuk navigasi kreator.

## Konfigurasi frontend lokal

Compose meneruskan `NEXT_PUBLIC_JEPRET_ENVIRONMENT` melalui substitution dengan default eksplisit `development`. Dengan demikian:

- `docker compose up` tetap mengaktifkan sandbox lokal secara default;
- root `.env` dapat mengubah build argument jika diperlukan;
- Dockerfile tetap default `production` ketika dibangun di luar Compose tanpa argument;
- README menjelaskan bahwa production configuration menyembunyikan kontrol simulasi, bukan menghapus seluruh string atau client code dari bundle.

Backend tetap menjadi security boundary; frontend gating hanya mencegah penyajian kontrol development kepada pengguna production.

## Error handling

- Environment backend hilang atau invalid: startup gagal melalui Pydantic validation; aplikasi tidak berjalan dalam mode development implisit.
- Kreator tanpa authorization pada booking: API mempertahankan response authorization yang sudah ada.
- Payment belum ada atau state tidak memenuhi syarat: payment page mempertahankan loading, empty, error, dan status-specific UI yang sudah ada.
- Jika seluruh jendela kandidat tanggal terpakai atau precondition response tidak valid, E2E gagal dengan pesan setup yang eksplisit dan tidak memutasi booking lain.

## Testing dan bukti penerimaan

Implementasi mengikuti TDD:

1. Tambahkan frontend test yang membuktikan link payment muncul untuk `confirmed` dan `completed`, lalu amati failure sebelum UI diubah.
2. Tambahkan backend configuration test yang membuktikan environment wajib, lalu amati failure sebelum default dihapus.
3. Perbarui E2E agar memakai tanggal unik dan jalur link kreator; jalankan focused E2E dua kali berurutan.
4. Jalankan focused backend payment/config tests dan seluruh frontend unit tests.
5. Jalankan full Playwright E2E.
6. Jalankan `npm run verify` dari repository root.
7. Jalankan `git diff --check`, secret scan, dan review transaction/idempotency untuk memastikan tidak ada perubahan domain yang tidak disengaja.
8. Ulangi spec review dan quality review sampai tidak ada Critical atau Important issue.

## Files yang diperkirakan berubah

- `apps/api/app/core/config.py`
- backend configuration/payment tests yang relevan
- `apps/web/src/app/booking/masuk/page.tsx`
- test halaman booking masuk
- `apps/web/e2e/booking.spec.ts`
- `.env.example`
- `docker-compose.yml`
- `README.md`
- `docs/testing.md` atau tracker hanya jika command/evidence berubah

Tidak ada Alembic migration yang diperlukan.

## Di luar scope

- Real payment provider, escrow, atau settlement.
- Payment notification baru.
- Admin cleanup endpoint atau test-only production route.
- Perubahan booking/payment state machine.
- Refactor unrelated pada booking list atau payment query architecture.

## Kriteria selesai

- API tidak dapat startup tanpa environment eksplisit.
- Compose lokal tetap berjalan sebagai development sandbox.
- Kreator dapat mencapai payment page dari booking confirmed dan completed.
- E2E release menggunakan link kreator dan lulus pada dua run berurutan.
- Full E2E dan `npm run verify` lulus.
- Dokumentasi sesuai dengan perilaku bundle dan Compose aktual.
- Spec review dan quality review menyatakan approved.
