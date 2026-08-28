# Panduan Deployment & Production Runbook — Jepret

Dokumen ini adalah panduan standar operasional produksi (_production runbook_) untuk menjalankan marketplace **Jepret** pada infrastruktur _cloud_ atau _self-hosted_.

---

## 1. Arsitektur Produksi

Arsitektur Jepret di produksi mempertahankan pola **Same-Origin Modular Monolith** dengan reverse-proxy gateway di garda depan:

```
[ Internet / Browser / Mobile PWA ]
                │ (HTTPS / Port 443)
                ▼
      [ Caddy Gateway / ALB ]
       │                   │
       ├─ /               ├─ /api/v1/*, /ws/*, /health, /ready
       ▼                   ▼
[ Next.js Web (SSR) ]   [ FastAPI API ]
                           │          │
                           ▼          ▼
           [ Managed PostgreSQL ]   [ Managed S3 / R2 Bucket ]
```

- **Domain Tunggal**: Seluruh request (Web, REST API, WebSocket) diarahkan ke satu domain publik (misal: `https://jepret.id`), menghindari isu CORS dan third-party cookie blocking pada Safari/iOS.
- **Private Network Isolation**: Database PostgreSQL dan Object Storage Bucket berada di jaringan VPC privat dan tidak diekspos langsung ke internet.

---

## 2. Environment Variables & Secret Management

Pada lingkungan produksi (`JEPRET_ENVIRONMENT=production`), nilai variabel environment **wajib** diinjeksi melalui Secret Manager (seperti AWS Secrets Manager, GCP Secret Manager, Vault, atau Doppler), bukan disimpan dalam file `.env` di server.

### Checklist Environment Variables:

| Variabel                       | Deskripsi                         | Rekomendasi Produksi                                                 |
| :----------------------------- | :-------------------------------- | :------------------------------------------------------------------- |
| `JEPRET_ENVIRONMENT`           | Lingkungan runtime                | Wajib `production`                                                   |
| `JEPRET_PUBLIC_ORIGIN`         | URL origin publik aplikasi        | `https://jepret.id`                                                  |
| `JEPRET_DATABASE_URL`          | Koneksi PostgreSQL asyncpg        | `postgresql+asyncpg://user:pass@db-pooler.internal:5432/jepret_prod` |
| `JEPRET_MINIO_ENDPOINT`        | Endpoint S3 storage internal      | `https://s3.ap-southeast-1.amazonaws.com`                            |
| `JEPRET_MINIO_PUBLIC_ENDPOINT` | Endpoint S3 storage untuk browser | `https://s3.ap-southeast-1.amazonaws.com`                            |
| `JEPRET_MINIO_ACCESS_KEY`      | IAM Access Key                    | Dibatasi hanya untuk bucket private                                  |
| `JEPRET_MINIO_SECRET_KEY`      | IAM Secret Key                    | Dari Secret Manager                                                  |
| `JEPRET_MINIO_PRIVATE_BUCKET`  | Nama bucket deliverables privat   | `jepret-private-prod`                                                |

---

## 3. Database Migration & Zero-Downtime Release

Migration skema database **tidak boleh** dijalankan di dalam container API saat aplikasi start. Migration harus dijalankan sebagai release job terpisah sebelum container baru di-traffic:

1. **Jalankan Migration Job**:
   ```bash
   uv run alembic upgrade head
   ```
2. **Backward Compatibility Rule**:
   - Seluruh migration database harus _backward-compatible_ dengan versi kode sebelumnya (menambahkan kolom baru dengan default/nullable, tidak langsung me-rename kolom aktif).
3. **Health & Readiness Check**:
   - Gateway memeriksa endpoint `/health` (liveness) dan `/ready` (database & dependency readiness).
   - Traffic hanya dialihkan ke instance baru setelah `/ready` mengembalikan `200 OK`.

---

## 4. Keamanan & Hardening Gateway

### TLS & Security Headers (Caddy)

Caddy secara otomatis mengelola sertifikat TLS Let's Encrypt / ZeroSSL dan menerapkan security headers:

```caddy
jepret.id {
  encode zstd gzip

  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    X-Frame-Options "DENY"
    X-Content-Type-Options "nosniff"
    Referrer-Policy "strict-origin-when-cross-origin"
    Permissions-Policy "camera=(), microphone=(), geolocation=()"
    -Server
  }

  handle /health {
    reverse_proxy api:8000
  }

  handle /ready {
    reverse_proxy api:8000
  }

  handle /api/v1/* {
    reverse_proxy api:8000
  }

  handle /ws/* {
    reverse_proxy api:8000
  }

  handle {
    reverse_proxy web:3000
  }
}
```

---

## 5. Backup & Disaster Recovery (DR)

1. **PostgreSQL Backup**:
   - Automated Daily Snapshot dengan retensi 30 hari.
   - Point-in-time recovery (PITR) diaktifkan dengan WAL archiving.
   - Uji pemulihan (_restore rehearsal_) dijadwalkan secara berkala per kuartal.
2. **Object Storage Backup**:
   - Bucket Versioning diaktifkan pada `jepret-private-prod`.
   - Cross-Region Replication (CRR) untuk backup geografis arsip deliverables.

---

## 6. Prosedur Rollback

Jika terjadi kendala kritis setelah deployment:

1. **Rollback Traffic Gateway / Container**:
   - Alihkan routing traffic gateway kembali ke image container versi sebelumnya yang stabil.
2. **Database Migration Rollback**:
   - Jika diperlukan downgrade skema:
   ```bash
   uv run alembic downgrade -1
   ```
3. **Post-Mortem**:
   - Periksa structured logs dan audit event `jepret.audit` untuk investigasi akar masalah.
