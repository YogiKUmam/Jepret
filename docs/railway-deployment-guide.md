# Panduan Deploy Jepret ke Railway.app (Full Online 24/7)

Panduan langkah demi langkah untuk men-deploy **Jepret** ke **Railway.app** agar aktif online 24 jam dan bisa diakses siapa saja dari internet.

---

## 1. Persiapan Awal

1. Buka [railway.app](https://railway.app) dan login/daftar menggunakan akun **GitHub** Anda.
2. Pastikan repository project Jepret sudah ada di akun GitHub Anda (jika belum, push branch ini ke GitHub).

---

## 2. Langkah Deploy di Railway

### Langkah 1: Buat Project Baru & Database PostgreSQL

1. Di Dashboard Railway, klik tombol **"+ New Project"**.
2. Pilih **"Provision PostgreSQL"**.
3. Railway akan membuat database PostgreSQL instan. Klik pada service PostgreSQL tersebut, buka tab **"Variables"**, dan salin nilai **`DATABASE_URL`** (atau Railway otomatis menyediakan referensi `${{Postgres.DATABASE_URL}}`).

---

### Langkah 2: Deploy Backend API (FastAPI)

1. Di project yang sama, klik **"+ New"** → **"GitHub Repo"** → Pilih repository Jepret Anda.
2. Buka tab **"Settings"** pada service tersebut:
   - **Service Name**: Ubah menjadi `jepret-api`.
   - **Dockerfile Path**: Isi dengan `apps/api/Dockerfile`.
3. Buka tab **"Variables"** dan tambahkan variabel environment berikut:

| Nama Variabel                  | Nilai                                                                 |
| :----------------------------- | :-------------------------------------------------------------------- |
| `JEPRET_ENVIRONMENT`           | `production`                                                          |
| `JEPRET_DATABASE_URL`          | `${{Postgres.DATABASE_URL}}` _(otomatis terhubung ke DB)_             |
| `JEPRET_PUBLIC_ORIGIN`         | `https://${{RAILWAY_PUBLIC_DOMAIN}}`                                  |
| `JEPRET_MINIO_ENDPOINT`        | `http://localhost:9000` _(atau URL Supabase Storage / Cloudflare R2)_ |
| `JEPRET_MINIO_PUBLIC_ENDPOINT` | `http://localhost:9000`                                               |
| `JEPRET_MINIO_ACCESS_KEY`      | `minioadmin`                                                          |
| `JEPRET_MINIO_SECRET_KEY`      | `minioadmin`                                                          |
| `JEPRET_MINIO_PRIVATE_BUCKET`  | `jepret-private`                                                      |

4. Buka tab **"Settings"** → pada bagian **"Networking"**, klik **"Generate Domain"** untuk mendapatkan URL publik API Anda (contoh: `https://jepret-api-production.up.railway.app`).
5. Jalankan migrasi database sekali via tab **"Deployments"** → **"Run Command"**:
   ```bash
   uv run alembic upgrade head
   uv run python scripts/seed.py
   ```

---

### Langkah 3: Deploy Frontend Web (Next.js)

1. Di project yang sama, klik **"+ New"** → **"GitHub Repo"** → Pilih repository yang sama.
2. Buka tab **"Settings"**:
   - **Service Name**: Ubah menjadi `jepret-web`.
   - **Dockerfile Path**: Isi dengan `apps/web/Dockerfile`.
3. Buka tab **"Variables"** dan tambahkan:

| Nama Variabel                    | Nilai        |
| :------------------------------- | :----------- |
| `NEXT_PUBLIC_JEPRET_ENVIRONMENT` | `production` |

4. Buka tab **"Settings"** → bagian **"Networking"**, klik **"Generate Domain"** (contoh: `https://jepret-production.up.railway.app`).

---

## 3. Menghubungkan APK Android ke URL Online

Setelah mendapatkan domain publik dari Railway (misal `https://jepret-production.up.railway.app`):

### Cara 1: Mengubah Langsung dari Aplikasi HP (Tanpa Build Ulang)

1. Buka aplikasi **Jepret** di HP Android Anda.
2. **Ketuk layar 3 kali secara cepat (_triple-tap_)**.
3. Masukkan domain Railway Anda:  
   `https://jepret-production.up.railway.app`
4. Tekan **Simpan**. Aplikasi akan langsung terhubung ke server cloud online!

### Cara 2: Build Ulang APK dengan Default URL Online

Ubah `default_server_url` di `apps/android/app/src/main/res/values/strings.xml`:

```xml
<string name="default_server_url">https://jepret-production.up.railway.app</string>
```

Lalu jalankan `.\gradlew.bat assembleDebug` di folder `apps/android` untuk menghasilkan `jepret-online.apk`.
