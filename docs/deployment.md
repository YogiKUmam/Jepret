# Catatan Deployment Jepret

**Production deployment tidak dilakukan pada Phase 1.** Foundation ini hanya menargetkan local development dan CI.

## Kebutuhan sebelum production (Phase 8 — Hardening)

- **HTTPS** — TLS termination pada gateway (Caddy mendukung ACME otomatis) dengan HSTS.
- **Managed PostgreSQL** — instance terkelola dengan backup otomatis, bukan container lokal.
- **S3-compatible object storage** — layanan terkelola menggantikan MinIO lokal; seluruh private URL harus signed.
- **Secret manager** — kredensial dari vault/secret manager, bukan file `.env`.
- **Migration job** — Alembic upgrade sebagai job terpisah sebelum rollout aplikasi, bukan saat container start.
- **Backup** — jadwal backup database dan object storage beserta uji restore berkala.
- **Rollback** — strategi rollback image aplikasi dan migration (downgrade path teruji) untuk setiap release.

## Prinsip

Arsitektur same-origin dipertahankan di production: satu domain publik, gateway meneruskan ke web dan API internal. PostgreSQL dan object storage tidak pernah diekspos publik.
