# Jepret Phase 2 — Auth & Profiles Design

**Tanggal:** 2026-07-17
**Status:** Approved
**Fase:** Phase 2 — Authentication dan client/creator profiles

## Keputusan produk (disetujui Bray)

1. **Metode auth:** email + password saja. Google OAuth ditunda.
2. **Model peran:** satu akun bisa dua peran. Semua user adalah client; profil kreator dapat diaktifkan kapan saja dari akun yang sama.
3. **Verifikasi kreator:** kreator submit profil → status `pending` → admin approve → tampil dengan badge TERVERIFIKASI. Approval memakai endpoint admin (UI admin penuh menyusul Phase 7).
4. **Fitur email:** verifikasi email dan reset password DITUNDA (belum ada email provider). Masuk fase hardening.

## Arsitektur auth

### Session cookie same-origin (sesuai ADR-001)

- Session opaque token (random 256-bit, URL-safe) disimpan sebagai **hash SHA-256** di tabel `sessions`; token mentah hanya ada di cookie.
- Cookie: `jepret_session`, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` saat production, umur 30 hari (sliding tidak dipakai; fixed expiry).
- Tanpa Redis — sessions di PostgreSQL (source of truth), sesuai asumsi Phase 0.
- Proteksi CSRF: kombinasi `SameSite=Lax` + middleware yang menolak method mutasi (`POST/PUT/PATCH/DELETE`) bila header `Origin` hadir dan tidak sama dengan `public_origin`.

### Password

- Hash memakai **Argon2id** via `pwdlib[argon2]`.
- Kebijakan: minimal 8 karakter (validasi Pydantic + zod di frontend).
- Login gagal mengembalikan error generik `INVALID_CREDENTIALS` (tanpa membocorkan email terdaftar atau tidak).

### Skema database (migration `0002`)

```text
users
  id UUID PK (default gen_random_uuid)
  email CITEXT/varchar UNIQUE NOT NULL (lowercased di aplikasi)
  password_hash VARCHAR NOT NULL
  full_name VARCHAR(100) NOT NULL
  is_admin BOOL NOT NULL DEFAULT false
  created_at / updated_at TIMESTAMPTZ (UTC)

sessions
  id UUID PK
  user_id UUID FK -> users ON DELETE CASCADE
  token_hash VARCHAR(64) UNIQUE NOT NULL
  expires_at TIMESTAMPTZ NOT NULL
  created_at TIMESTAMPTZ
  INDEX (user_id), INDEX (expires_at)

creator_profiles
  id UUID PK
  user_id UUID FK UNIQUE -> users ON DELETE CASCADE  (1-1)
  display_name VARCHAR(100) NOT NULL
  city VARCHAR(100) NOT NULL
  bio TEXT NOT NULL DEFAULT ''
  specialty VARCHAR(50) NOT NULL            -- mis. wedding, produk, keluarga
  starting_price_idr BIGINT NOT NULL CHECK >= 0
  status VARCHAR(20) NOT NULL DEFAULT 'draft'  -- draft|pending|approved|rejected
  submitted_at / reviewed_at TIMESTAMPTZ NULL
  created_at / updated_at TIMESTAMPTZ
```

Admin pertama dibuat lewat **seed script** (bukan register endpoint).

## Kontrak API (`/api/v1`)

Envelope konsisten Phase 1: sukses `{"data": ...}`, error `{"error": {code, message, details}}`.

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| POST | `/api/v1/auth/register` | publik | Daftar (email, password, full_name) → auto-login, set cookie |
| POST | `/api/v1/auth/login` | publik | Login → set cookie |
| POST | `/api/v1/auth/logout` | session | Hapus session + clear cookie |
| GET | `/api/v1/auth/me` | session | Profil user aktif + creator_profile ringkas |
| PATCH | `/api/v1/profiles/me` | session | Update full_name |
| PUT | `/api/v1/profiles/me/creator` | session | Buat/ubah draft profil kreator (status kembali `draft` bila sudah `rejected`) |
| POST | `/api/v1/profiles/me/creator/submit` | session | `draft → pending` (validasi kelengkapan) |
| GET | `/api/v1/admin/creator-applications` | admin | Daftar profil `pending` |
| POST | `/api/v1/admin/creator-applications/{id}/approve` | admin | `pending → approved` |
| POST | `/api/v1/admin/creator-applications/{id}/reject` | admin | `pending → rejected` |

Error codes baru: `EMAIL_TAKEN`, `INVALID_CREDENTIALS`, `UNAUTHENTICATED` (401), `FORBIDDEN` (403), `CREATOR_PROFILE_INCOMPLETE`, `INVALID_STATUS_TRANSITION`.

Aturan AGENTS.md yang berlaku: setiap endpoint di-authorize; permission tests wajib untuk admin routes dan kepemilikan profil; transisi status kreator dalam transaksi.

## Frontend (mobile-first, Bahasa Indonesia)

- Route baru: `/daftar`, `/masuk`, `/profil` (protected), `/profil/kreator` (form + status pengajuan).
- API client tipis berbasis `fetch` (`credentials: "same-origin"`) dengan tipe dari `@jepret/contracts`.
- State auth: TanStack Query `["auth","me"]`; guard client-side redirect ke `/masuk` bila 401.
- Form: `react-hook-form` + `zod` (sudah dipin di Phase 1); tombol/input min-h-11; state loading/empty/error/success lengkap.
- Bottom navigation item **Profil** menjadi link aktif ke `/profil` (item lain tetap non-interaktif).

## Seeding & akun demo

Script `apps/api/scripts/seed_demo.py` (idempotent, dijalankan via `docker compose run --rm migrate` terpisah / `uv run`):

- `admin@jepret.local` / `admin12345` — admin
- `klien@jepret.local` / `klien12345` — client biasa
- `kreator@jepret.local` / `kreator12345` — kreator `approved` ("Studio Cahaya", Bandung, wedding, Rp1.500.000)

README bagian "Akun demo" diperbarui. Password demo hanya untuk lokal.

## Di luar scope Phase 2

Reset password, verifikasi email, OAuth, rate limiting login (dicatat sebagai risiko ke hardening), upload avatar/portfolio (fase marketplace), halaman admin ber-UI (Phase 7 — sementara via API/docs), listing kreator publik (Phase 3).

## Risiko & mitigasi

- **Brute force login:** tanpa rate limit dulu; dicatat di docs/deployment.md untuk hardening.
- **Session bocor via log:** token tidak pernah di-log; hanya hash yang disimpan.
- **Timezone:** semua timestamp UTC (`TIMESTAMPTZ`), tampilan Asia/Jakarta menyusul di frontend fase berikutnya.
