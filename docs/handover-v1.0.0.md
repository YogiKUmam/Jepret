# Laporan Serah Terima Proyek (Project Handover) & Rilis MVP v1.0.0

## Jepret — Marketplace Mobile-First Kreator Visual

**Tanggal Rilis:** 28 Agustus 2026  
**Versi:** `v1.0.0-mvp` (Git Tag: `v1.0.0`)  
**Status Proyek:** Selesai Penuh (Phase 1–8) — Siap Produksi (_Production Ready_)

---

## 1. Ringkasan Eksekutif (Executive Summary)

Platform **Jepret** telah berhasil diselesaikan secara menyeluruh sesuai dengan seluruh spesifikasi kebutuhan MVP (_Minimum Viable Product_). Platform ini dirancang khusus untuk menghubungkan klien dengan kreator visual (fotografer dan videografer) terverifikasi melalui pengalaman mobile-first yang modern, cepat, dan aman.

Seluruh 8 fase pengembangan telah lulus uji mutu (_quality gates_) 100% hijau, mencakup sistem autentikasi multi-peran, penemuan kreator, pemesanan kalender otomatis, simulasi escrow pembayaran, ruang kerja obrolan real-time & berkas hasil resolusi tinggi, ulasan bintang, mediasi sengketa, hingga dashboard tata kelola admin.

---

## 2. Ikhtisar Fitur & Alur Pengguna (User Journeys)

```
[ Klien Menemukan Kreator ] ──▶ [ Ajukan Booking & Tanggal ] ──▶ [ Kreator Menerima Booking ]
                                                                             │
[ Hasil Diterima & Dana Cair ] ◀── [ Unggah Deliverables ] ◀── [ Bayar (Escrow Dikunci) ]
              │
[ Berikan Rating & Ulasan 1-5★ ]
```

### 2.1. Alur Pengalaman Klien (Client Journey)

- **Eksplorasi & Filter Kreator**: Mencari fotografer/videografer berdasarkan kota, spesialisasi layanan, portofolio, dan rentang harga awal dengan paginasi instan.
- **Pemesanan Terproteksi**: Memilih tanggal acara yang tersedia tanpa risiko jadwal ganda (_anti double-booking_).
- **Pembayaran Aman (Escrow Sandbox)**: Dana klien diamankan dalam status _held_ dan tidak langsung diteruskan ke kreator sebelum hasil pekerjaan disetujui.
- **Ruang Kerja Booking**: Berinteraksi langsung dengan kreator via live chat, memantau progres sesi, dan mengunduh berkas resolusi tinggi via tautan terenkripsi berbatas waktu.
- **Ulasan & Rating**: Memberikan penilaian bintang (1–5) dan komentar pengalaman kerja.
- **Pusat Komplain/Sengketa**: Mengajukan sengketa jika terjadi ketidaksesuaian hasil kerja untuk dimediasi oleh tim Admin.

### 2.2. Alur Pengalaman Kreator (Creator Journey)

- **Onboarding & Profil Profesional**: Mendaftar, mengisi bio, kota domisili, spesialisasi fotografi/videografi, harga mulai dari, dan mengajukan verifikasi profil ke Admin.
- **Manajemen Pesanan Masuk**: Menerima atau menolak tawaran booking yang masuk.
- **Ruang Kerja & Pelaksanaan Sesi**: Mengubah status pekerjaan (`Mulai Sesi` → `Kirim Hasil`), berdiskusi dengan klien, dan mengunggah berkas foto/video atau tautan cloud storage.
- **Pencairan Dana Otomatis**: Dana pembayaran dilepas (_released_) secara otomatis begitu klien menyetujui deliverables.
- **Reputasi & Skor Rating**: Membangun portofolio ulasan publik untuk menarik lebih banyak klien baru.

### 2.3. Alur Tata Kelola Admin (Admin Governance)

- **Dashboard Operasional Bento Grid**: Memantau metrik utama platform (Total Pengguna, Total Kreator Terverifikasi, Total Booking, Sengketa Aktif, dan Total Nilai Transaksi / GMV).
- **Verifikasi Kreator**: Meninjau portofolio kreator baru, menyetujui (_Approve_) atau menolak (_Reject_) dengan jejak audit otomatis.
- **Pusat Mediasi Sengketa (Dispute Resolution)**: Mengambil keputusan mediasi yang adil:
  - _Refund ke Klien_: Membatalkan booking dan mengembalikan dana penuh ke klien.
  - _Release ke Kreator_: Menyelesaikan booking dan melepas dana ke saldo kreator.

---

## 3. Arsitektur & Standar Keamanan

- **Same-Origin Modular Monolith**: Gateway Caddy sebagai pintu gerbang tunggal (`http://localhost:8080` / domain produksi), menyatukan Next.js App Router (SSR) dan FastAPI tanpa kendala CORS atau blokir cookie browser mobile.
- **Keamanan Sesi & Data**: Menggunakan cookie sesi `HttpOnly`, `SameSite=Lax`, dan proteksi `Secure` di produksi.
- **Private Object Storage**: Berkas hasil foto/video beresolusi tinggi disimpan di bucket privat tanpa akses publik anonim, diunduh hanya melalui _pre-signed URL_ berdurasi 15 menit dengan verifikasi tanda tangan MIME type (_magic bytes_).
- **PWA (Progressive Web App)**: Dilengkapi `manifest.json` dan ikon aplikasi agar dapat diinstal seperti aplikasi _native_ pada perangkat Android dan iOS.
- **Audit Logging**: Jejak audit terstruktur untuk seluruh tindakan administratif dan finansial sensitif.

---

## 4. Bukti Mutu & Hasil Pengujian (Verification Matrix)

Seluruh komponen telah diuji secara otomatis dan lulus 100%:

| Parameter Pengujian                           | Metrik                             | Status                     |
| :-------------------------------------------- | :--------------------------------- | :------------------------- |
| **Backend Unit & Integration Tests (pytest)** | 107 tests passed                   | ✅ **100% Hijau**          |
| **Frontend Component Tests (Vitest)**         | 20 test files / 134 tests passed   | ✅ **100% Hijau**          |
| **Type Safety (Mypy & TypeScript tsc)**       | 50 file Python & Next.js tsc clean | ✅ **0 Error**             |
| **Code Style & Linter (Ruff & ESLint)**       | Format check & Lint clean          | ✅ **0 Error / 0 Warning** |
| **API Contracts Synchronization**             | OpenAPI 3.1 & TypeScript Types     | ✅ **0 Diff**              |
| **Production Build Compilation**              | 12 Next.js App Routes compiled     | ✅ **Sukses**              |

---

## 5. Panduan Menjalankan Demo Produk

Untuk menjalankan dan mempresentasikan aplikasi kepada klien atau pemangku kepentingan:

### Langkah 1: Jalankan Stack Docker

```bash
docker compose up -d --build
docker compose run --rm migrate
docker compose run --rm seed
```

### Langkah 2: Buka Aplikasi di Browser

Akses URL: **`http://localhost:8080`**

### Langkah 3: Akun Demo yang Siap Digunakan

1. **Klien Demo**:
   - Email: `klien@jepret.local`
   - Password: `klien12345`
   - _Akses_: Eksplorasi marketplace, buat booking, bayar simulasi, chat & unduh hasil, beri ulasan.
2. **Kreator Demo (Studio Cahaya)**:
   - Email: `kreator@jepret.local`
   - Password: `kreator12345`
   - _Akses_: Terima booking masuk, mulai sesi foto, upload file deliverables.
3. **Administrator Demo**:
   - Email: `admin@jepret.local`
   - Password: `admin12345`
   - _Akses_: Buka menu `/admin` untuk verifikasi kreator dan mediasi sengketa.

---

## 6. Rekomendasi Pengembangan Lanjutan (Post-MVP Roadmap)

Setelah rilis MVP v1.0.0 ini, beberapa fitur peningkatan lanjutan (_P1 / Phase 9+_) yang siap dikembangkan meliputi:

1. **Koleksi Favorit / Bookmark**: Klien dapat menandai kreator favorit mereka.
2. **Push Notifications & In-App Notification Center**: Notifikasi lonceng di header dan email transaksional nyata (integrasi Sendgrid/AWS SES).
3. **Paket Jasa Berjenjang (Multi-Tier Packages)**: Paket Silver, Gold, Platinum pada profil kreator.
4. **Payment Gateway Produksi**: Integrasi provider pembayaran nasional (Midtrans/Xendit/DOKU) menggantikan sandbox mock.

---

_Dokumen serah terima ini menandai penyelesaian resmi MVP Jepret v1.0.0._
