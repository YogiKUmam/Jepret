# Asumsi Jepret Phase 0–1

- Target pertama adalah local development dan CI, bukan cloud production.
- Smartphone PWA adalah client utama; desktop memakai codebase yang sama.
- Caddy adalah same-origin gateway.
- PostgreSQL adalah source of truth.
- MinIO hanya storage provider lokal; private URL selalu signed pada fase fitur.
- Redis opsional dan tidak boleh diperlukan oleh stack dasar.
- Authentication, marketplace, booking, payment, chat, dan admin tidak termasuk Phase 1.
- UI memakai Bahasa Indonesia; code dan identifier memakai Bahasa Inggris.
- Datetime disimpan UTC dan kelak ditampilkan dengan zona Asia/Jakarta.
