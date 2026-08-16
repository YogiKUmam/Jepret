# Desain Phase 6 — Chat, Deliverables, dan Penyelesaian Booking

**Tanggal:** 2026-08-16

**Status:** Disetujui

**Cakupan:** Phase 6 MVP

## Ringkasan

Phase 6 menghadirkan booking workspace mobile-first yang menyatukan chat,
lampiran privat, deliverables, dan progress pekerjaan. Alur transaksi yang
sebelumnya berhenti pada booking `confirmed` diselesaikan menjadi
`confirmed → in_progress → delivered → completed`. Kreator memulai sesi dan
mengirim hasil, sedangkan klien menerima hasil. Penerimaan klien melepaskan
pembayaran melalui `PaymentProvider` secara idempotent.

Database tetap menjadi source of truth. REST menyimpan pesan dan aksi bisnis,
WebSocket menyiarkan perubahan secara real-time pada satu API instance, dan
cursor polling menjadi fallback ketika koneksi terputus. Redis tidak menjadi
dependency wajib. File privat disimpan pada MinIO/S3-compatible storage dan
hanya diakses melalui signed URL yang diterbitkan setelah authorization.

## Tujuan

- Memberikan satu ruang kerja per booking untuk klien dan kreator.
- Menyediakan chat real-time yang tetap berfungsi saat WebSocket terputus.
- Mendukung pesan teks dan lampiran privat berukuran terbatas.
- Mendukung deliverable berupa file privat atau tautan HTTPS eksternal.
- Menyelesaikan state machine pekerjaan dan release payment sesuai brief MVP.
- Menjaga authorization, transaction, idempotency, dan privasi object storage.
- Mempertahankan modular monolith serta mode development tanpa Redis.

## Non-tujuan

- Typing indicator, reactions, edit/delete message, thread, group chat, dan
  push notification.
- Redis Pub/Sub atau fan-out multi-instance.
- Video privat berukuran besar dan transcoding.
- Antivirus production-grade; kebutuhan ini menjadi bagian Phase 8.
- Akses admin ke isi chat/file sebelum dispute aktif.
- UI dispute, review, dan dashboard admin; semuanya masuk Phase 7.

## Keputusan produk

1. Deliverable mendukung file privat dan tautan eksternal.
2. Chat dapat ditulis setelah booking `confirmed` dan menjadi read-only pada
   `completed` atau `cancelled`.
3. Real-time memakai WebSocket, database, dan polling fallback tanpa Redis.
4. Chat mendukung plain text dan lampiran privat JPEG, PNG, WebP, atau PDF
   sampai 10 MB.
5. Booking memperoleh status `in_progress` dan `delivered`.
6. Deliverable dapat dihapus sebelum booking `delivered`; setelah diterbitkan,
   record bersifat immutable. Revisi ditambahkan sebagai versi baru.
7. Admin hanya dapat membaca isi ketika ada dispute aktif pada Phase 7 dan
   akses tersebut harus diaudit.
8. UI memakai satu booking workspace, bukan halaman chat dan hasil yang
   terpisah tanpa konteks.

## Arsitektur

Phase 6 menambah empat boundary di modular monolith FastAPI:

- `conversations`: conversation, message, read state, pagination, dan
  participant authorization;
- `storage`: upload intent, object verification, signed upload/download, dan
  storage adapter;
- `deliverables`: file/link hasil, versioning, publish, dan immutability;
- `bookings`: state transition pekerjaan serta koordinasi release payment.

Route handler tetap tipis. Service memegang authorization dan domain rule.
Storage adapter mengisolasi MinIO dari domain. WebSocket connection manager
hanya menangani koneksi lokal dan broadcast setelah database commit; ia tidak
menjadi source of truth.

Pada web, `/booking/[id]` menjadi workspace role-aware. Feature code tetap
dikelompokkan per domain (`conversations`, `deliverables`, `bookings`) dan
menggunakan API/auth flow same-origin yang sudah ada.

## State machine booking dan payment

Alur utama:

```text
confirmed --creator starts--> in_progress
in_progress --creator publishes deliverables--> delivered
delivered --client accepts--> completed
```

Aturan:

- `confirmed → in_progress` hanya dapat dilakukan kreator terkait dan hanya
  ketika payment berstatus `held`.
- `in_progress → delivered` hanya dapat dilakukan kreator terkait jika ada
  minimal satu deliverable yang valid.
- `delivered → completed` hanya dapat dilakukan klien pemilik booking.
- Penerimaan klien mengunci booking dan payment, meminta provider release,
  menerapkan event secara idempotent, lalu mengisi `completed_at`. Booking
  tidak menjadi `completed` jika release gagal.
- Replay penerimaan setelah sukses mengembalikan state yang sama tanpa
  memanggil provider dua kali.
- `in_progress` dan `delivered` tetap termasuk status yang memblokir tanggal
  kreator.
- Pembatalan biasa hanya berlaku sebelum `in_progress`. Konflik setelah sesi
  dimulai diarahkan ke dispute pada Phase 7.
- Status `completed` dan `cancelled` tetap terminal.

Endpoint completion lama tidak boleh mempertahankan jalur kreator
`confirmed → completed`. Kontrak dimigrasikan menjadi aksi penerimaan klien
dari `delivered`, dan seluruh web, seed, contracts, serta regresi Phase 5 ikut
diperbarui.

## Model data

### Booking

Constraint status diperluas dengan `in_progress` dan `delivered`. Tambahkan:

- `started_at TIMESTAMPTZ NULL`;
- `delivered_at TIMESTAMPTZ NULL`;
- `completed_at` tetap digunakan untuk penerimaan akhir.

Partial unique index tanggal aktif mencakup `accepted`, `awaiting_payment`,
`confirmed`, `in_progress`, dan `delivered`.

### Conversation

- `id UUID PK`;
- `booking_id UUID FK UNIQUE NOT NULL`;
- `created_at`, `updated_at` UTC.

Conversation dibuat secara lazy pada akses pertama ketika booking berstatus
`confirmed`, `in_progress`, atau `delivered`. Conversation yang sudah ada tetap
dapat dibaca setelah booking menjadi `completed` atau `cancelled`, tetapi tidak
menerima pesan baru. Booking yang dibatalkan sebelum conversation pernah aktif
tidak membuat conversation baru.

### Message

- `id UUID PK`;
- `conversation_id UUID FK NOT NULL`;
- `sender_user_id UUID FK NOT NULL`;
- `client_message_id UUID NOT NULL`;
- `message_type`: `text`, `attachment`, atau `system`;
- `body TEXT NULL`;
- metadata attachment: `upload_id`, display filename, MIME, dan size;
- `read_at TIMESTAMPTZ NULL`;
- `created_at`, `edited_at NULL`.

Unique constraint `(conversation_id, sender_user_id, client_message_id)`
menjamin retry pesan tidak menggandakan data. `edited_at` disediakan untuk
kompatibilitas model brief, tetapi edit pesan tidak diekspos pada MVP.

### Upload intent

- `id UUID PK`;
- `booking_id UUID FK NOT NULL`;
- `requested_by_user_id UUID FK NOT NULL`;
- `purpose`: `chat_attachment` atau `deliverable`;
- `object_key TEXT UNIQUE NOT NULL`;
- expected filename, MIME, dan size;
- `status`: `pending`, `completed`, `expired`, atau `rejected`;
- `expires_at`, `completed_at`, `created_at`.

Intent sekali pakai. Completion diverifikasi dengan object metadata dari
storage dan tidak dapat dipindahkan ke booking atau purpose lain.

### Deliverable

- `id UUID PK`;
- `booking_id UUID FK NOT NULL`;
- `uploaded_by_user_id UUID FK NOT NULL`;
- `title`, `description NULL`;
- `source_type`: `private_file` atau `external_link`;
- `upload_id UUID FK NULL` atau `external_url TEXT NULL`, tepat satu terisi;
- `media_type`, filename, MIME, size bila file privat;
- `replaces_deliverable_id UUID FK NULL` untuk versi revisi;
- `created_at`.

Check constraint memastikan source konsisten. Record yang sudah menjadi bagian
dari publish `delivered` tidak diubah atau dihapus. Revisi bersifat append-only
dan menunjuk versi sebelumnya. Workflow meminta revisi ditambahkan pada Phase
7; modelnya disiapkan sekarang tanpa membuka jalur admin.

## API

Semua response memakai envelope dan error contract yang sudah ada.

### Workspace dan conversation

- `GET /api/v1/bookings/{booking_id}/workspace`
- `GET /api/v1/bookings/{booking_id}/conversation`
- `GET /api/v1/conversations/{conversation_id}/messages?cursor=&limit=`
- `POST /api/v1/conversations/{conversation_id}/messages`
- `POST /api/v1/conversations/{conversation_id}/read`
- `WS /ws/conversations/{conversation_id}`

REST POST adalah satu-satunya jalur penulisan pesan. WebSocket mengirim event
`message.created`, `message.read`, dan `booking.updated`. Client melakukan
deduplication berdasarkan message ID dan selalu dapat mengejar state melalui
REST cursor.

### Storage

- `POST /api/v1/bookings/{booking_id}/uploads`
- `POST /api/v1/uploads/{upload_id}/complete`
- `POST /api/v1/uploads/{upload_id}/download`

Create mengembalikan signed PUT URL singkat. Complete melakukan `HEAD`,
memverifikasi size/MIME, dan mengubah intent sekali. Download memverifikasi
participant authorization lalu mengembalikan signed GET URL singkat.

### Deliverables dan transitions

- `GET /api/v1/bookings/{booking_id}/deliverables`
- `POST /api/v1/bookings/{booking_id}/deliverables`
- `DELETE /api/v1/deliverables/{deliverable_id}` sebelum publish
- `POST /api/v1/bookings/{booking_id}/start`
- `POST /api/v1/bookings/{booking_id}/deliver`
- `POST /api/v1/bookings/{booking_id}/complete` oleh klien dari `delivered`

External URL wajib absolut, memakai HTTPS, dan tidak di-fetch server. Host
ditampilkan kepada pengguna. API tidak menyimpan signed URL; hanya object key
dan metadata yang stabil.

## WebSocket dan fallback

Handshake memvalidasi session cookie, `Origin`, conversation, dan participant.
Outsider mendapat close code kebijakan tanpa membocorkan isi conversation.
Koneksi hanya subscribe; penulisan tetap melalui REST.

Setelah message atau transition berhasil commit, service menerbitkan event ke
connection manager lokal. Kehilangan broadcast tidak menghilangkan data.
Client melakukan reconnect dengan backoff, refetch saat tersambung kembali,
poll setiap lima detik ketika disconnected, dan refetch saat tab kembali
aktif. Desain ini benar untuk satu API instance; multi-instance Pub/Sub menjadi
hardening terpisah.

## Storage dan validasi file

- Bucket `jepret-private` tidak public-readable.
- Object key dibuat server-side dengan namespace purpose/booking dan UUID;
  nama file pengguna tidak menjadi path.
- Signed PUT berlaku singkat dan dibatasi pada satu object key.
- Attachment chat menerima JPEG, PNG, WebP, dan PDF sampai 10 MB.
- Deliverable menerima JPEG, PNG, WebP, PDF, dan ZIP sampai 100 MB.
- Video atau hasil yang lebih besar memakai external HTTPS link.
- Completion menolak object hilang, size berbeda, MIME tidak diizinkan, intent
  kedaluwarsa, sudah dipakai, atau dimiliki pihak lain.
- Download URL singkat diterbitkan ulang bila kedaluwarsa.
- Orphan object dari intent kedaluwarsa dicatat untuk cleanup pada maintenance;
  tidak pernah otomatis dianggap sebagai deliverable.

Validasi MIME menggabungkan deklarasi intent, metadata object, dan signature
file untuk format yang didukung. ZIP tidak diekstrak server. Virus scanning
production-grade menjadi requirement Phase 8 sebelum deployment publik.

## Authorization dan privasi

- Klien pemilik dan kreator terkait dapat membaca workspace, chat, dan hasil.
- Hanya keduanya dapat membuka WebSocket conversation.
- Hanya kreator terkait dapat memulai sesi, membuat/menghapus deliverable
  sebelum publish, dan mengirim hasil.
- Hanya klien pemilik dapat menerima hasil.
- Admin ditolak pada Phase 6. Phase 7 dapat memberi akses terbatas ketika
  dispute aktif dengan audit log eksplisit.
- Authorization selalu server-side pada setiap route dan tidak bergantung pada
  visibilitas tombol web.
- Chat dan upload memakai rate limit per session/user dan booking yang dapat
  berjalan in-process tanpa Redis. Limit terdistribusi lintas instance menjadi
  bagian hardening Phase 8.
- Origin check, cookie policy, correlation ID, dan consistent API errors yang
  sudah ada tetap berlaku.
- Body chat, title, dan description disimpan dan dirender sebagai plain text.
  Tidak ada rich HTML.

## Pengalaman pengguna

Kartu booking `confirmed`, `in_progress`, `delivered`, dan `completed`
menampilkan **Buka ruang kerja**. Workspace memiliki:

- header kode booking, pihak terkait, jadwal, dan status;
- progress Terkonfirmasi → Sedang berlangsung → Hasil dikirim → Selesai;
- tab **Chat** dan **Hasil**;
- composer mobile dengan upload progress dan status koneksi;
- unread badge pada kartu booking;
- action role-aware: **Mulai sesi**, **Kirim hasil**, atau **Terima hasil**;
- tampilan read-only untuk booking terminal.

Target sentuh minimal 44 px, focus state terlihat, tab dan form dapat digunakan
dengan keyboard, serta pesan baru diumumkan secara sopan melalui `aria-live`
tanpa memindahkan fokus.

## Error handling

- WebSocket putus menampilkan **Menghubungkan ulang** dan mengaktifkan polling.
- Retry POST message memakai `client_message_id` yang sama.
- Upload memiliki progress, cancel, error, dan retry; record bisnis baru dibuat
  setelah completion terverifikasi.
- Signed URL kedaluwarsa meminta URL baru tanpa mengekspos object key.
- Stale transition menghasilkan error Indonesia dan refetch workspace.
- Gagal release provider tidak mengubah booking menjadi `completed`; retry aman.
- Error tidak mencatat cookie, token, message body, URL privat, atau metadata
  provider sensitif.

## Transaction dan concurrency

- State transition mengunci row booking dengan `SELECT ... FOR UPDATE`.
- Action yang menyentuh payment juga mengunci row payment dalam urutan tetap.
- Message insert dan deduplication terjadi dalam satu transaction.
- Publish `delivered` mengunci booking dan memastikan deliverable masih valid.
- Delete deliverable mengunci booking dan menolak status `delivered` ke atas.
- Upload completion menggunakan conditional transition `pending → completed`.
- Provider release memakai payment UUID sebagai idempotency key stabil dan
  event application mengikuti boundary Phase 5. Jika provider sudah berhasil
  tetapi commit database gagal, retry meminta atau menerima kembali state
  provider yang sama lalu menerapkan event secara idempotent. Booking hanya
  selesai setelah event release valid tersimpan.

## Migration dan compatibility

Alembic migration Phase 6:

1. mengganti booking status check constraint;
2. memperluas partial unique active-date index;
3. menambah timestamp booking;
4. membuat conversations, messages, upload intents, dan deliverables beserta
   FK, unique, check constraint, serta index pagination.

Migration harus memiliki downgrade yang valid. Data booking lama tetap sah.
Booking `completed` lama tetap terminal. Perubahan semantics `/complete`
disertai generated contract baru, UI baru, release notes dokumentasi, dan
perubahan seluruh caller/test dalam repository; tidak ada compatibility shim
yang memungkinkan kreator melewati delivery acceptance.

Seed menambah minimal satu workspace aktif dengan message history dan satu
deliverable demo. Seed idempoten dan tidak bergantung pada signed URL yang
kedaluwarsa.

## Testing dan quality gates

### Unit dan integration API

- state transition, role, held-payment precondition, dan timestamp;
- participant/outsider/admin authorization pada seluruh REST dan WebSocket;
- cursor pagination stabil tanpa duplikasi;
- duplicate `client_message_id` mengembalikan message yang sama;
- terminal conversation read-only;
- upload expiry, ownership, purpose, MIME, size, signature, dan one-time use;
- private download hanya untuk participant;
- deliverable source check, delete-before-publish, dan immutability;
- concurrent start/deliver/complete dan provider release tepat sekali;
- MinIO signed PUT/HEAD/GET integration.

### Web

- loading, empty, error, reconnecting, upload, read-only, dan success state;
- role/status action matrix dan protected-data boundary;
- message deduplication, cursor merge, polling fallback, dan reconnect refetch;
- accessible tabs, form labels, focus, live region, serta 44 px touch target.

### E2E

Playwright mobile memakai dua session terisolasi dan membuktikan:

1. booking dibayar sampai `confirmed`;
2. kedua pihak bertukar chat dan lampiran;
3. kreator memulai sesi;
4. kreator menambah private deliverable dan external link;
5. kreator mengirim hasil;
6. klien membuka hasil melalui authorized URL dan menerima hasil;
7. booking menjadi `completed` dan payment `released` sekali;
8. chat terminal read-only dan outsider tetap ditolak;
9. reconnect/polling tidak menggandakan message.

Final gate mencakup formatter, lint, mypy, TypeScript, unit/integration tests,
contract generation check, Next.js build, Compose config, rebuild stack,
migration, seed idempoten, focused E2E berulang, full E2E, security diff review,
dan root `npm run verify`.

## Acceptance criteria

Phase 6 selesai hanya jika:

- booking workspace berfungsi bagi klien dan kreator pada mobile;
- chat durable, real-time, retry-safe, dan memiliki polling fallback;
- private file tidak dapat dibaca tanpa authorization dan signed URL;
- deliverable file/link mengikuti lifecycle dan immutability;
- state machine lengkap sampai client acceptance dan released payment;
- seluruh permission, transaction, concurrency, dan idempotency test hijau;
- Compose lokal, migration, seed, E2E, build, dan `npm run verify` hijau;
- docs dan tracker fase diperbarui dengan bukti aktual.
