# Jepret Phase 6 Chat and Deliverables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a secure mobile-first booking workspace with durable real-time chat, private attachments, versioned deliverables, and the complete `confirmed → in_progress → delivered → completed/released` transaction flow.

**Architecture:** PostgreSQL is the source of truth; thin FastAPI routes call focused conversation, upload, deliverable, and booking services. REST persists mutations, an in-process WebSocket hub broadcasts committed events, and cursor polling recovers missed events without Redis. A boto3-backed storage adapter uses an internal MinIO endpoint for server operations and a public local endpoint only for short-lived signed browser URLs.

**Tech Stack:** Python 3.13, FastAPI 0.139, SQLAlchemy 2.0 async, PostgreSQL 18, Alembic, boto3, MinIO/S3, pytest, Next.js 16, React 19, TypeScript strict, TanStack Query, Vitest/Testing Library, Playwright mobile Chromium, Docker Compose, Caddy.

---

## Execution rules

- Work in the existing isolated worktree on branch `codex/phase-5-payment`.
- Follow `AGENTS.md`, the approved design, and TDD: RED, minimal GREEN, focused regression, then commit.
- Do not combine independent tasks into one commit. Use the exact commit message listed for each task.
- Every authorization-sensitive route needs owner, counterparty, outsider, and admin-denied coverage.
- Every booking/payment transition needs row-lock, transaction, concurrency, and idempotency review.
- Run `git diff --check` and a changed-file secret scan before every commit.
- Do not push until Task 12 passes final spec review and quality review.

## File map

### API and persistence

- Modify `apps/api/app/db/models.py`: Phase 6 ORM models, constraints, relationships, and booking states.
- Create `apps/api/migrations/versions/20260816_0006_chat_deliverables.py`: schema migration and downgrade.
- Create `apps/api/app/api/workspace_schemas.py`: conversation, message, upload, deliverable, and workspace contracts.
- Create `apps/api/app/services/workspace_access.py`: shared booking participant lookup and role checks.
- Create `apps/api/app/services/conversations.py`: lazy conversation creation, message persistence, pagination, read state.
- Create `apps/api/app/services/uploads.py`: upload intent lifecycle and object verification.
- Create `apps/api/app/services/deliverables.py`: deliverable creation, deletion, listing, and publish rules.
- Modify `apps/api/app/services/bookings.py`: start, deliver, client completion, cancellation boundary.
- Modify `apps/api/app/services/payments.py`: idempotent client-acceptance release helper.
- Create `apps/api/app/integrations/storage.py`: S3 protocol, boto3 adapter, MIME signature validation.
- Create `apps/api/app/core/rate_limit.py`: bounded in-process fixed-window limiter.
- Create `apps/api/app/realtime.py`: process-local WebSocket connection hub.
- Create `apps/api/app/api/conversations.py`: REST and WebSocket conversation routes.
- Create `apps/api/app/api/uploads.py`: signed upload, completion, and download routes.
- Create `apps/api/app/api/deliverables.py`: deliverable routes.
- Modify `apps/api/app/api/bookings.py`: workspace and lifecycle routes.
- Modify `apps/api/app/api/schemas.py`: booking timestamps/status output.
- Modify `apps/api/app/main.py`: register Phase 6 routers.
- Modify `apps/api/app/core/config.py`, `apps/api/pyproject.toml`, `apps/api/uv.lock`: storage public endpoint and dependency.

### Web

- Modify `apps/web/src/lib/api.ts`: Phase 6 strict domain types.
- Create `apps/web/src/lib/workspaces.ts`: workspace query and lifecycle mutations.
- Create `apps/web/src/lib/conversations.ts`: message pagination, send/read mutations, WebSocket fallback.
- Create `apps/web/src/lib/uploads.ts`: XHR signed upload with progress and retry-safe completion.
- Create `apps/web/src/lib/deliverables.ts`: deliverable mutations and authorized download.
- Create `apps/web/src/components/workspace/workspace-header.tsx`: status progress and role actions.
- Create `apps/web/src/components/workspace/conversation-panel.tsx`: accessible message list/composer/reconnect state.
- Create `apps/web/src/components/workspace/deliverables-panel.tsx`: file/link form, list, download, publish state.
- Create `apps/web/src/components/workspace/upload-field.tsx`: file validation and progress UI.
- Create `apps/web/src/app/booking/[id]/page.tsx`: integrated booking workspace.
- Create `apps/web/src/app/booking/[id]/page.test.tsx`: workspace state and accessibility coverage.
- Modify booking list pages, booking card, payment page tests, and booking libraries for new status/actions.

### Infrastructure, contracts, seed, and evidence

- Create `infra/minio/cors.xml`: local private-bucket browser CORS.
- Modify `docker-compose.yml`, `docker-compose.debug.yml`, `.env.example`, `.github/workflows/ci.yml`.
- Modify `apps/api/scripts/seed_demo.py` and `apps/api/tests/test_seed_demo.py`.
- Regenerate `packages/contracts/openapi.json` and `packages/contracts/src/schema.d.ts`.
- Create `apps/web/e2e/workspace.spec.ts` and update `apps/web/e2e/booking.spec.ts` status handling.
- Modify `README.md`, `docs/architecture.md`, `docs/testing.md`, and `docs/implementation-plan.md` after actual verification.

## Task 1: Add Phase 6 schema and ORM models

**Files:**

- Create: `apps/api/migrations/versions/20260816_0006_chat_deliverables.py`
- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/tests/test_phase6_schema.py`

- [ ] **Step 1: Write the failing PostgreSQL schema tests**

Create integration tests that upgrade to head and assert the new constraints. Use direct SQL so the tests prove the database, not only ORM metadata:

```python
@pytest.mark.integration
async def test_phase6_schema_enforces_booking_and_upload_invariants() -> None:
    async with fresh_connection() as connection:
        statuses = await connection.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_booking_status_valid'"
            )
        )
        assert "in_progress" in statuses
        assert "delivered" in statuses

        tables = set(
            (
                await connection.scalars(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            ).all()
        )
        assert {"conversations", "messages", "upload_intents", "deliverables"} <= tables
```

Add a second test that inserts two active bookings for one creator/date and proves `in_progress` and `delivered` participate in `uq_bookings_active_date`.

- [ ] **Step 2: Run the schema tests to verify RED**

Run:

```powershell
uv run --project apps/api pytest apps/api/tests/test_phase6_schema.py -m integration -q
```

Expected: FAIL because migration `20260816_0006` and the four tables do not exist.

- [ ] **Step 3: Add the migration**

The migration must:

```python
revision = "20260816_0006"
down_revision = "20260731_0005"

ACTIVE_STATUS_SQL = (
    "status IN ('accepted', 'awaiting_payment', 'confirmed', "
    "'in_progress', 'delivered')"
)
BOOKING_STATUS_SQL = (
    "status IN ('requested', 'accepted', 'awaiting_payment', 'confirmed', "
    "'in_progress', 'delivered', 'rejected', 'completed', 'cancelled')"
)
```

Drop/recreate `ck_booking_status_valid` and `uq_bookings_active_date`, add
`started_at` and `delivered_at`, then create the four tables with these
database invariants:

```python
sa.UniqueConstraint("booking_id", name="uq_conversation_booking")
sa.UniqueConstraint(
    "conversation_id", "sender_user_id", "client_message_id",
    name="uq_message_client_id",
)
sa.CheckConstraint(
    "purpose IN ('chat_attachment', 'deliverable')",
    name="ck_upload_purpose_valid",
)
sa.CheckConstraint(
    "status IN ('pending', 'completed', 'expired', 'rejected')",
    name="ck_upload_status_valid",
)
sa.CheckConstraint(
    "(source_type = 'private_file' AND upload_id IS NOT NULL AND external_url IS NULL) "
    "OR (source_type = 'external_link' AND upload_id IS NULL AND external_url IS NOT NULL)",
    name="ck_deliverable_source_valid",
)
```

Create indexes `ix_messages_conversation_created_id`,
`ix_upload_intents_expiry`, and `ix_deliverables_booking_created`. Make
`messages.upload_id` and `deliverables.upload_id` unique nullable foreign keys
to prevent one completed intent being consumed twice.

Downgrade must delete Phase 6 rows, map `in_progress` and `delivered` back to
`confirmed`, remove new columns/tables, and restore the Phase 5 constraint and
index.

- [ ] **Step 4: Add matching typed ORM models**

Extend `BOOKING_STATUSES` and add relationships from `Booking`. Define focused
models with `Mapped` types:

```python
class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    booking: Mapped[Booking] = relationship(back_populates="conversation")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class UploadIntent(TimestampMixin, Base):
    __tablename__ = "upload_intents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Add `Message` and `Deliverable` with the exact columns/constraints from the
approved spec. Use strings for persisted states, consistent with existing
models, and typed constants for allowed values.

- [ ] **Step 5: Run migration upgrade, schema tests, downgrade, and re-upgrade**

Run:

```powershell
uv run --project apps/api alembic upgrade head
uv run --project apps/api pytest apps/api/tests/test_phase6_schema.py -m integration -q
uv run --project apps/api alembic downgrade 20260731_0005
uv run --project apps/api alembic upgrade head
```

Expected: schema tests PASS; downgrade and re-upgrade exit 0.

- [ ] **Step 6: Run ORM quality gates and commit**

```powershell
uv run --project apps/api ruff format apps/api/app/db/models.py apps/api/migrations/versions/20260816_0006_chat_deliverables.py apps/api/tests/test_phase6_schema.py
uv run --project apps/api ruff check apps/api/app/db/models.py apps/api/migrations/versions/20260816_0006_chat_deliverables.py apps/api/tests/test_phase6_schema.py
uv run --project apps/api mypy apps/api/app
git diff --check
git add apps/api/app/db/models.py apps/api/migrations/versions/20260816_0006_chat_deliverables.py apps/api/tests/test_phase6_schema.py
git commit -m "feat(api): add chat and deliverable schema"
```

## Task 2: Add private S3 storage configuration and adapter

**Files:**

- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/uv.lock`
- Modify: `apps/api/app/core/config.py`
- Create: `apps/api/app/integrations/storage.py`
- Create: `apps/api/tests/test_storage_adapter.py`
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/api/tests/conftest.py`

- [ ] **Step 1: Write failing config and adapter tests**

Add a required setting and prove signing uses the public endpoint while object
inspection uses the internal client:

```python
def test_settings_require_public_storage_endpoint() -> None:
    values = complete_settings_values()
    values.pop("minio_public_endpoint")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_storage_rejects_mismatched_signature() -> None:
    assert sniff_content_type(b"%PDF-1.7\n") == "application/pdf"
    with pytest.raises(StorageValidationError):
        validate_signature("image/png", b"%PDF-1.7\n")
```

Use fake boto clients to assert `generate_presigned_url` is called on the public
client and `head_object`/ranged `get_object` on the internal client.

- [ ] **Step 2: Run focused tests to verify RED**

```powershell
uv run --project apps/api pytest apps/api/tests/test_config.py apps/api/tests/test_storage_adapter.py -q
```

Expected: FAIL because `minio_public_endpoint` and storage adapter do not exist.

- [ ] **Step 3: Add boto3 and required settings**

Run `uv add --project apps/api boto3`, retain the exact resolver-selected
version in `pyproject.toml`, and commit the generated `uv.lock` change.

Add:

```python
minio_public_endpoint: AnyHttpUrl
minio_private_bucket: str = Field(default="jepret-private", min_length=1)
storage_signed_url_ttl_seconds: int = Field(default=600, ge=60, le=3600)
```

Extend `VALID_STARTUP_ENVIRONMENT`, config tests, CI env, and `.env.example` in
later infrastructure Task 3; until then focused tests set these values locally.

- [ ] **Step 4: Implement the storage protocol and boto3 adapter**

Define:

```python
@dataclass(frozen=True)
class StoredObject:
    size_bytes: int
    content_type: str
    signature: bytes


class StorageAdapter(Protocol):
    async def create_upload_url(
        self, *, object_key: str, content_type: str, expires_seconds: int
    ) -> str:
        raise NotImplementedError

    async def inspect_object(self, *, object_key: str) -> StoredObject:
        raise NotImplementedError

    async def create_download_url(self, *, object_key: str, expires_seconds: int) -> str:
        raise NotImplementedError

    async def delete_object(self, *, object_key: str) -> None:
        raise NotImplementedError
```

`Boto3StorageAdapter` creates two path-style S3 clients with the same
credentials: internal `minio_endpoint` for network operations and
`minio_public_endpoint` for URL signing. Wrap each boto3 call with
`anyio.to_thread.run_sync`. `inspect_object` runs `head_object` and a
`Range="bytes=0-15"` read. Validate signatures for JPEG, PNG, WebP, PDF, and
ZIP without extracting archives.

- [ ] **Step 5: Run focused tests and static checks**

```powershell
uv run --project apps/api pytest apps/api/tests/test_config.py apps/api/tests/test_storage_adapter.py -q
uv run --project apps/api ruff check apps/api/app/integrations/storage.py apps/api/tests/test_storage_adapter.py
uv run --project apps/api mypy apps/api/app
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/api/pyproject.toml apps/api/uv.lock apps/api/app/core/config.py apps/api/app/integrations/storage.py apps/api/tests/test_config.py apps/api/tests/test_storage_adapter.py apps/api/tests/conftest.py
git commit -m "feat(api): add private storage adapter"
```

## Task 3: Make local and CI MinIO usable by signed browser uploads

**Files:**

- Create: `infra/minio/cors.xml`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.debug.yml`
- Modify: `.env.example`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/architecture.md`
- Create: `apps/api/tests/test_storage_integration.py`

- [ ] **Step 1: Write the failing MinIO integration test**

The test requests a signed PUT, uploads a small PNG signature with `httpx`,
inspects it through the internal adapter, requests a signed GET, and asserts
the same bytes are returned. It must also assert an unknown key is rejected.

```python
@pytest.mark.integration
async def test_signed_put_and_get_round_trip() -> None:
    key = f"integration/{uuid.uuid4()}.png"
    upload_url = await STORAGE.create_upload_url(
        object_key=key, content_type="image/png", expires_seconds=120
    )
    payload = b"\x89PNG\r\n\x1a\n" + b"jepret-test"
    async with httpx.AsyncClient() as client:
        put = await client.put(upload_url, content=payload, headers={"Content-Type": "image/png"})
        assert put.status_code == 200
        download_url = await STORAGE.create_download_url(object_key=key, expires_seconds=120)
        downloaded = await client.get(download_url)
        assert downloaded.content == payload
```

Use `finally` to delete the object.

- [ ] **Step 2: Run to verify infrastructure RED**

```powershell
uv run --project apps/api pytest apps/api/tests/test_storage_integration.py -m integration -q
```

Expected: FAIL because the public endpoint/CORS/base Compose port are not configured.

- [ ] **Step 3: Configure loopback-only local access and CORS**

Create `infra/minio/cors.xml`:

```xml
<CORSConfiguration>
  <CORSRule>
    <AllowedOrigin>http://localhost:8080</AllowedOrigin>
    <AllowedMethod>GET</AllowedMethod>
    <AllowedMethod>PUT</AllowedMethod>
    <AllowedHeader>*</AllowedHeader>
    <ExposeHeader>ETag</ExposeHeader>
    <MaxAgeSeconds>3600</MaxAgeSeconds>
  </CORSRule>
</CORSConfiguration>
```

Bind MinIO API as `127.0.0.1:9000:9000` in base Compose, leave console port
`9001` only in the debug override, mount the CORS file read-only into
`minio-init`, and run:

```sh
mc cors set local/jepret-private /config/cors.xml
```

Add API env:

```yaml
JEPRET_MINIO_PUBLIC_ENDPOINT: http://localhost:9000
JEPRET_MINIO_PRIVATE_BUCKET: jepret-private
```

Clarify in architecture docs that the endpoint is network-addressable for
signed requests but the bucket never allows anonymous public read.

- [ ] **Step 4: Start MinIO and rerun integration**

```powershell
docker compose up -d minio minio-init
uv run --project apps/api pytest apps/api/tests/test_storage_integration.py -m integration -q
```

Expected: PASS.

- [ ] **Step 5: Add CI preparation**

Set `JEPRET_MINIO_PUBLIC_ENDPOINT=http://localhost:9000` in the quality job and
add `docker compose up -d minio minio-init` before integration tests. Keep the
full E2E job unchanged except for using the updated Compose definition.

- [ ] **Step 6: Validate Compose and commit**

```powershell
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.debug.yml config --quiet
git diff --check
git add infra/minio/cors.xml docker-compose.yml docker-compose.debug.yml .env.example .github/workflows/ci.yml docs/architecture.md apps/api/tests/test_storage_integration.py
git commit -m "feat(infra): enable signed private uploads"
```

## Task 4: Implement upload intents and authorization

**Files:**

- Create: `apps/api/app/api/workspace_schemas.py`
- Create: `apps/api/app/services/workspace_access.py`
- Create: `apps/api/app/services/uploads.py`
- Create: `apps/api/app/api/uploads.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_uploads_api.py`

- [ ] **Step 1: Write failing authorization and lifecycle tests**

Cover client/creator participants, outsider, admin, wrong purpose, expiry,
one-time completion, size mismatch, MIME mismatch, signature mismatch, and
download authorization. Core expectations:

```python
created = client.post(
    f"/api/v1/bookings/{booking_id}/uploads",
    json={
        "purpose": "chat_attachment",
        "filename": "brief.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
    },
)
assert created.status_code == 201
assert "object_key" not in created.json()["data"]

outsider = outsider_client.post(f"/api/v1/uploads/{upload_id}/download")
assert outsider.status_code == 404
```

Inject a fake `StorageAdapter` through a module-level provider setter/fixture;
never contact MinIO in these API tests.

- [ ] **Step 2: Run focused tests to verify RED**

```powershell
uv run --project apps/api pytest apps/api/tests/test_uploads_api.py -m integration -q
```

Expected: FAIL with 404 because routes do not exist.

- [ ] **Step 3: Implement shared participant access**

Create a single helper used by every Phase 6 domain:

```python
@dataclass(frozen=True)
class BookingAccess:
    booking: Booking
    role: Literal["client", "creator"]


async def require_booking_participant(
    db: AsyncSession, *, booking_id: UUID, user: User, lock: bool = False
) -> BookingAccess:
    stmt = select(Booking).where(Booking.id == booking_id)
    if lock:
        stmt = stmt.with_for_update()
    booking = await db.scalar(stmt.options(selectinload(Booking.creator_profile)))
    if booking is None:
        raise booking_not_found()
    if booking.client_id == user.id:
        return BookingAccess(booking, "client")
    if booking.creator_profile.user_id == user.id:
        return BookingAccess(booking, "creator")
    raise booking_not_found()
```

Use 404 for non-participants to avoid resource enumeration.

- [ ] **Step 4: Implement upload schemas and service**

Schemas must constrain purpose, filename, MIME, and positive size. Service
constants:

```python
UPLOAD_LIMITS = {
    "chat_attachment": (10 * 1024 * 1024, frozenset({
        "image/jpeg", "image/png", "image/webp", "application/pdf"
    })),
    "deliverable": (100 * 1024 * 1024, frozenset({
        "image/jpeg", "image/png", "image/webp", "application/pdf", "application/zip"
    })),
}
UPLOAD_TTL = timedelta(minutes=10)
```

Generate `object_key` as
`{purpose}/{booking_id}/{uuid4().hex}`. Do not include the user filename. On
completion, lock the intent, verify ownership/participant/status/expiry, call
`inspect_object`, compare exact size/content type/signature, set `completed`,
and commit. Return signed URLs but never object keys.

- [ ] **Step 5: Add thin routes and app registration**

Routes:

```python
@router.post("/bookings/{booking_id}/uploads", status_code=201)
async def create_upload(
    booking_id: UUID, payload: CreateUploadRequest, user: CurrentUser, db: DbSession
) -> UploadEnvelope:
    data = await upload_service.create_intent(
        db, booking_id=booking_id, user=user, payload=payload
    )
    return UploadEnvelope(data=data)

@router.post("/uploads/{upload_id}/complete")
async def complete_upload(
    upload_id: UUID, user: CurrentUser, db: DbSession
) -> UploadEnvelope:
    data = await upload_service.complete_intent(db, upload_id=upload_id, user=user)
    return UploadEnvelope(data=data)

@router.post("/uploads/{upload_id}/download")
async def download_upload(
    upload_id: UUID, user: CurrentUser, db: DbSession
) -> SignedUrlEnvelope:
    data = await upload_service.authorize_download(db, upload_id=upload_id, user=user)
    return SignedUrlEnvelope(data=data)
```

- [ ] **Step 6: Run tests, static checks, and commit**

```powershell
uv run --project apps/api pytest apps/api/tests/test_uploads_api.py -m integration -q
uv run --project apps/api ruff check apps/api/app/api/uploads.py apps/api/app/services/uploads.py apps/api/app/services/workspace_access.py apps/api/app/api/workspace_schemas.py
uv run --project apps/api mypy apps/api/app
git diff --check
git add apps/api/app/api/workspace_schemas.py apps/api/app/services/workspace_access.py apps/api/app/services/uploads.py apps/api/app/api/uploads.py apps/api/app/main.py apps/api/tests/test_uploads_api.py
git commit -m "feat(api): authorize private upload intents"
```

## Task 5: Implement durable conversation REST and rate limiting

**Files:**

- Create: `apps/api/app/core/rate_limit.py`
- Create: `apps/api/app/services/conversations.py`
- Create: `apps/api/app/api/conversations.py`
- Modify: `apps/api/app/api/uploads.py`
- Modify: `apps/api/app/api/workspace_schemas.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_conversations_api.py`
- Create: `apps/api/tests/test_rate_limit.py`

- [ ] **Step 1: Write failing conversation tests**

Cover lazy creation only for `confirmed|in_progress|delivered`, terminal
read-only, canceled-before-confirmation returning no conversation, participant
authorization, admin denial, text/attachment validation, upload ownership and
purpose, duplicate client ID, stable cursor, and read receipts.

```python
payload = {"client_message_id": str(uuid.uuid4()), "message_type": "text", "body": "Halo"}
first = client.post(f"/api/v1/conversations/{conversation_id}/messages", json=payload)
replay = client.post(f"/api/v1/conversations/{conversation_id}/messages", json=payload)
assert first.status_code == replay.status_code == 201
assert first.json()["data"]["id"] == replay.json()["data"]["id"]
```

Cursor test inserts equal timestamps and proves `(created_at,id)` order yields
every message exactly once.

- [ ] **Step 2: Run focused tests to verify RED**

```powershell
uv run --project apps/api pytest apps/api/tests/test_conversations_api.py apps/api/tests/test_rate_limit.py -m integration -q
```

Expected: FAIL because service/routes/limiter do not exist.

- [ ] **Step 3: Implement a bounded in-process limiter**

Use a monotonic fixed window guarded by `asyncio.Lock`:

```python
class FixedWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: float, max_keys: int = 10_000) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._entries: dict[str, Window] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str, now: float | None = None) -> bool:
        resolved_now = time.monotonic() if now is None else now
        async with self._lock:
            self._prune(resolved_now)
            window = self._entries.get(key)
            if window is None or resolved_now >= window.reset_at:
                self._entries[key] = Window(1, resolved_now + self.window_seconds)
                return True
            if window.count >= self.limit:
                return False
            self._entries[key] = Window(window.count + 1, window.reset_at)
            return True
```

Evict expired entries first and the oldest reset window when `max_keys` is
reached. Use 30 message writes/minute/user/conversation and 10 upload intents/
minute/user/booking. Wire the upload limiter into `api/uploads.py` here and add
a focused API assertion that request 11 returns `429 RATE_LIMITED` without
creating another intent.

- [ ] **Step 4: Implement conversation service**

Use a typed keyset cursor encoding UTC timestamp plus UUID with URL-safe base64.
Public service signatures:

```python
async def get_or_create_for_booking(
    db: AsyncSession, *, booking_id: UUID, user: User
) -> Conversation | None:
    raise NotImplementedError

async def list_messages(
    db: AsyncSession, *, conversation_id: UUID, user: User,
    cursor: str | None, limit: int
) -> MessagePage:
    raise NotImplementedError

async def create_message(
    db: AsyncSession, *, conversation_id: UUID, user: User,
    client_message_id: UUID, message_type: str,
    body: str | None, upload_id: UUID | None
) -> tuple[Message, bool]:
    raise NotImplementedError

async def mark_read(
    db: AsyncSession, *, conversation_id: UUID, user: User
) -> ReadReceipt:
    raise NotImplementedError
```

Trim text, cap body at 2,000 characters, require text xor completed
`chat_attachment`, and commit before returning. On unique collision, rollback
and return the existing message only if all immutable fields match; otherwise
raise `IDEMPOTENCY_CONFLICT`.

- [ ] **Step 5: Add routes and unread counts**

Add the approved endpoints plus
`GET /api/v1/conversations/unread`, which returns one aggregate query mapping
booking IDs to unread counts for the current user. Do not perform one query per
booking.

- [ ] **Step 6: Run focused and booking regression tests**

```powershell
uv run --project apps/api pytest apps/api/tests/test_conversations_api.py apps/api/tests/test_rate_limit.py apps/api/tests/test_bookings_api.py -m integration -q
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```powershell
git add apps/api/app/core/rate_limit.py apps/api/app/services/conversations.py apps/api/app/api/conversations.py apps/api/app/api/uploads.py apps/api/app/api/workspace_schemas.py apps/api/app/main.py apps/api/tests/test_conversations_api.py apps/api/tests/test_rate_limit.py
git commit -m "feat(api): add durable booking conversations"
```

## Task 6: Add authenticated WebSocket broadcast and polling recovery contract

**Files:**

- Create: `apps/api/app/realtime.py`
- Modify: `apps/api/app/api/conversations.py`
- Modify: `apps/api/app/api/bookings.py`
- Create: `apps/api/tests/test_conversation_websocket.py`

- [ ] **Step 1: Write failing WebSocket tests**

Create two authenticated `TestClient` sessions for the booking participants.
Assert participant broadcast, outsider/admin close, wrong Origin close, invalid
frame close, ping/pong, disconnect cleanup, and terminal read-only behavior.

```python
with creator.websocket_connect(
    f"/ws/conversations/{conversation_id}",
    headers={"origin": "http://localhost:8080"},
) as socket:
    sent = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"client_message_id": str(uuid.uuid4()), "message_type": "text", "body": "Siap"},
    )
    event = socket.receive_json()
    assert event == {"type": "message.created", "data": sent.json()["data"]}
```

- [ ] **Step 2: Run to verify RED**

```powershell
uv run --project apps/api pytest apps/api/tests/test_conversation_websocket.py -m integration -q
```

Expected: FAIL because `/ws/conversations/{id}` does not exist.

- [ ] **Step 3: Implement the process-local hub**

```python
class ConnectionHub:
    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, conversation_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[conversation_id].add(websocket)

    async def disconnect(self, conversation_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(conversation_id)
            if sockets is not None:
                sockets.discard(websocket)
                if not sockets:
                    self._connections.pop(conversation_id, None)
```

`broadcast` snapshots connections under the lock, sends outside the lock, and
removes failed sockets. It must never make the committed REST request fail.

- [ ] **Step 4: Implement explicit WebSocket auth and Origin validation**

Read `jepret_session` from cookies, compare Origin to normalized
`settings.public_origin`, load the user with a request-scoped DB session, and
call the same participant service as REST. Close with 4401 for missing/invalid
session, 4403 for Origin/participant denial, and 1003 for non-ping client
frames. Do not disclose conversation existence in close reasons.

- [ ] **Step 5: Broadcast only after committed mutations**

Message route broadcasts `message.created`; read route broadcasts
`message.read`; booking/deliver routes broadcast `booking.updated`. Build event
payloads from response schemas, never ORM objects or internal object keys.

- [ ] **Step 6: Run WebSocket, security, and probe regressions**

```powershell
uv run --project apps/api pytest apps/api/tests/test_conversation_websocket.py -m integration -q
uv run --project apps/api pytest apps/api/tests/test_websocket_probe.py apps/api/tests/test_security.py -q
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```powershell
git add apps/api/app/realtime.py apps/api/app/api/conversations.py apps/api/app/api/bookings.py apps/api/tests/test_conversation_websocket.py
git commit -m "feat(api): stream authorized conversation events"
```

## Task 7: Add deliverables and publish rules

**Files:**

- Create: `apps/api/app/services/deliverables.py`
- Create: `apps/api/app/api/deliverables.py`
- Modify: `apps/api/app/api/workspace_schemas.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_deliverables_api.py`

- [ ] **Step 1: Write failing deliverable tests**

Cover private file and external HTTPS link, exact-one-source validation,
creator-only writes, participant reads, outsider/admin denial, HTTP/exotic URL
rejection, no server fetch, delete before publish, immutable after publish, and
append-only `replaces_deliverable_id` integrity.

```python
external = creator.post(
    f"/api/v1/bookings/{booking_id}/deliverables",
    json={
        "title": "Galeri final",
        "description": "Unduh dalam 30 hari",
        "source_type": "external_link",
        "external_url": "https://gallery.example/final",
    },
)
assert external.status_code == 201
assert external.json()["data"]["external_host"] == "gallery.example"
```

- [ ] **Step 2: Run focused tests to verify RED**

```powershell
uv run --project apps/api pytest apps/api/tests/test_deliverables_api.py -m integration -q
```

Expected: FAIL because routes do not exist.

- [ ] **Step 3: Implement schemas and service**

Use a discriminated union request:

```python
class PrivateDeliverableRequest(BaseModel):
    source_type: Literal["private_file"]
    title: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    upload_id: UUID


class ExternalDeliverableRequest(BaseModel):
    source_type: Literal["external_link"]
    title: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    external_url: AnyHttpUrl
```

Reject non-HTTPS URLs after parsing. Create/delete only for related creator in
`in_progress`; private upload must be completed, owned by the creator, purpose
`deliverable`, same booking, and unused. List for both participants in
`created_at,id` order. Delete locks booking and deliverable, then deletes the
record; object deletion happens after DB commit and failure is logged for
maintenance rather than rolling back a valid DB decision.

- [ ] **Step 4: Add thin routes and app registration**

Expose approved GET/POST/DELETE endpoints. Output returns a `downloadable`
boolean and external host but never object key or a long-lived private URL.
After each committed create/delete, broadcast a sanitized `deliverable.updated`
event through the hub created in Task 6. Storage cleanup failure must not alter
the committed event.

- [ ] **Step 5: Run focused tests and commit**

```powershell
uv run --project apps/api pytest apps/api/tests/test_deliverables_api.py apps/api/tests/test_uploads_api.py -m integration -q
uv run --project apps/api ruff check apps/api/app/services/deliverables.py apps/api/app/api/deliverables.py
uv run --project apps/api mypy apps/api/app
git add apps/api/app/services/deliverables.py apps/api/app/api/deliverables.py apps/api/app/api/workspace_schemas.py apps/api/app/main.py apps/api/tests/test_deliverables_api.py
git commit -m "feat(api): manage private booking deliverables"
```

## Task 8: Complete the booking lifecycle and release payment on client acceptance

**Files:**

- Modify: `apps/api/app/services/bookings.py`
- Modify: `apps/api/app/services/payments.py`
- Modify: `apps/api/app/api/bookings.py`
- Modify: `apps/api/app/api/schemas.py`
- Modify: `apps/api/tests/test_bookings_api.py`
- Modify: `apps/api/tests/test_payments_api.py`
- Create: `apps/api/tests/test_workspace_lifecycle.py`

- [ ] **Step 1: Write failing transition and authorization tests**

Test creator `start`, creator `deliver` with at least one deliverable, client
`complete`, wrong roles, no held payment, no deliverable, ordinary cancellation
blocked after start, active-date blocking, stale/concurrent actions, provider
failure rollback, duplicate completion, and provider success followed by a
simulated DB conflict/retry.

```python
started = creator.post(f"/api/v1/bookings/{booking_id}/start")
assert started.json()["data"]["status"] == "in_progress"

delivered = creator.post(f"/api/v1/bookings/{booking_id}/deliver")
assert delivered.json()["data"]["status"] == "delivered"

completed = client.post(f"/api/v1/bookings/{booking_id}/complete")
replay = client.post(f"/api/v1/bookings/{booking_id}/complete")
assert completed.status_code == replay.status_code == 200
assert completed.json()["data"]["status"] == "completed"
assert payment_state(booking_id) == "released"
assert provider.release_calls == 1
```

- [ ] **Step 2: Run focused tests to verify RED**

```powershell
uv run --project apps/api pytest apps/api/tests/test_workspace_lifecycle.py apps/api/tests/test_payments_api.py -m integration -q
```

Expected: new tests FAIL because start/deliver/client completion do not exist.

- [ ] **Step 3: Implement start and deliver transitions**

```python
async def start_booking(db: AsyncSession, *, booking_id: UUID, user: User) -> Booking:
    booking = await _locked_booking(db, booking_id)
    await _require_creator(db, booking, user)
    _require_status(booking, frozenset({"confirmed"}))
    await payment_service.require_held_payment_for_locked_booking(db, booking)
    booking.status = "in_progress"
    booking.started_at = datetime.now(UTC)
    await db.commit()
    return await get_for_user(db, booking_id=booking.id, user=user)
```

`deliver_booking` uses the same lock order, requires `in_progress`, counts at
least one deliverable, sets `delivered`/`delivered_at`, and commits.
Create a plain-text `system` message for successful start, deliver, and client
acceptance in the same transaction when a conversation exists. Broadcast the
committed `booking.updated` and `message.created` payloads afterward.

- [ ] **Step 4: Implement idempotent client completion and release**

Replace creator completion with client-only acceptance. Lock booking then
payment. If already `completed` with released payment, return current state.
For `delivered` + `held`, call `PROVIDER.release_payment(payment.id)` using the
stable payment UUID, stage the normalized event, set booking completed before
event transition validation, and commit both together. If provider raises,
rollback. If the provider event already exists after a commit race, load and
return the committed released state.

Update `_apply_transition` so a release event is valid only while the service
is completing a `delivered` booking or replaying an already completed booking;
never permit a creator/dev endpoint to transition held funds early.

- [ ] **Step 5: Update cancellation and API outputs**

`ACTIVE_STATUSES` remains only pre-work states. Add `started_at`, `delivered_at`,
and `completed_at` to `BookingOut`. Add POST `/start` and `/deliver`; retain
POST `/complete` path with new client semantics. Remove creator release controls
from web in Task 11; keep the development simulate-release endpoint as an
idempotent inspection/replay endpoint that cannot release a held non-completed
payment.

- [ ] **Step 6: Run full booking/payment integration tests**

```powershell
uv run --project apps/api pytest apps/api/tests/test_bookings_api.py apps/api/tests/test_payments_api.py apps/api/tests/test_workspace_lifecycle.py apps/api/tests/test_deliverables_api.py -m integration -q
```

Expected: all PASS with only the documented upstream Starlette/httpx warning.

- [ ] **Step 7: Commit**

```powershell
git add apps/api/app/services/bookings.py apps/api/app/services/payments.py apps/api/app/api/bookings.py apps/api/app/api/schemas.py apps/api/tests/test_bookings_api.py apps/api/tests/test_payments_api.py apps/api/tests/test_workspace_lifecycle.py
git commit -m "feat(api): complete booking delivery lifecycle"
```

## Task 9: Add workspace aggregate contract, seed data, and generated contracts

**Files:**

- Modify: `apps/api/app/api/bookings.py`
- Modify: `apps/api/app/api/workspace_schemas.py`
- Modify: `apps/api/scripts/seed_demo.py`
- Modify: `apps/api/tests/test_seed_demo.py`
- Modify: `packages/contracts/openapi.json`
- Modify: `packages/contracts/src/schema.d.ts`

- [ ] **Step 1: Write failing workspace and seed tests**

Workspace response must include participant role, booking, nullable
conversation, ordered deliverables, unread count, and payment summary without
internal payment/storage fields. Seed test runs twice and proves one demo
conversation, deterministic messages, and one external deliverable remain.

```python
workspace = client.get(f"/api/v1/bookings/{booking_id}/workspace")
assert workspace.status_code == 200
assert workspace.json()["data"]["role"] == "client"
assert "object_key" not in workspace.text
assert "raw_metadata" not in workspace.text
```

- [ ] **Step 2: Run tests to verify RED**

```powershell
uv run --project apps/api pytest apps/api/tests/test_seed_demo.py -q
uv run --project apps/api pytest apps/api/tests/test_workspace_lifecycle.py -m integration -q
```

Expected: FAIL because workspace aggregate and Phase 6 seed are absent.

- [ ] **Step 3: Implement workspace aggregate**

Add `GET /api/v1/bookings/{id}/workspace`. Reuse participant access,
conversation lookup without creating for pre-confirmed terminal bookings,
deliverable list, aggregate unread query, and sanitized payment summary. Use a
single transaction snapshot and bounded query count; add an integration test
that counts SQL statements to prevent N+1 regressions.

- [ ] **Step 4: Extend the idempotent demo seed**

Add `in_progress` and `delivered` booking scenarios, deterministic conversation
messages keyed by booking/scenario, and an external deliverable
`https://example.com/jepret-demo-gallery`. Re-running seed updates known rows,
does not duplicate messages/deliverables, and never stores signed URLs.

- [ ] **Step 5: Generate and validate contracts**

```powershell
npm run contracts:generate
npm run contracts:check
```

Expected: generated files include Phase 6 routes/statuses and the check has no
remaining diff after generation is staged.

- [ ] **Step 6: Run focused tests and commit**

```powershell
uv run --project apps/api pytest apps/api/tests/test_seed_demo.py -q
uv run --project apps/api pytest apps/api/tests/test_workspace_lifecycle.py -m integration -q
git add apps/api/app/api/bookings.py apps/api/app/api/workspace_schemas.py apps/api/scripts/seed_demo.py apps/api/tests/test_seed_demo.py packages/contracts/openapi.json packages/contracts/src/schema.d.ts
git commit -m "feat(api): expose booking workspace contract"
```

## Task 10: Build strict web data clients, signed upload, and realtime fallback

**Files:**

- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/lib/bookings.ts`
- Create: `apps/web/src/lib/workspaces.ts`
- Create: `apps/web/src/lib/conversations.ts`
- Create: `apps/web/src/lib/uploads.ts`
- Create: `apps/web/src/lib/deliverables.ts`
- Create: `apps/web/src/lib/conversations.test.tsx`
- Create: `apps/web/src/lib/uploads.test.ts`

- [ ] **Step 1: Write failing hook and upload tests**

Test message cursor merge/deduplication, stable `client_message_id` retry,
WebSocket event invalidation, disconnect polling every five seconds, reconnect
refetch, focus refetch, upload progress/cancel/retry, direct PUT without session
cookie, and upload completion through same-origin API.

```tsx
it("polls only while the socket is disconnected", async () => {
  vi.useFakeTimers();
  renderHook(() => useConversation("conversation-1"), { wrapper });
  socket.close();
  await vi.advanceTimersByTimeAsync(5_000);
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/conversations/conversation-1/messages"),
    expect.anything(),
  );
});
```

- [ ] **Step 2: Run tests to verify RED**

```powershell
npm --workspace @jepret/web test -- src/lib/conversations.test.tsx src/lib/uploads.test.ts
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Add strict Phase 6 types and query keys**

Extend `BookingStatus` with `in_progress|delivered` and define exact
`Workspace`, `Conversation`, `Message`, `MessagePage`, `UploadIntent`, and
`Deliverable` interfaces matching generated OpenAPI. Centralize keys:

```typescript
export const workspaceKey = (bookingId: string) => ["workspace", bookingId] as const;
export const messageKey = (conversationId: string) =>
  ["conversations", conversationId, "messages"] as const;
export const unreadKey = ["conversations", "unread"] as const;
```

- [ ] **Step 4: Implement WebSocket with polling fallback**

Use `new WebSocket(`${protocol}//${location.host}/ws/conversations/${id}`)`.
On validated known event types, merge `message.created` by ID or invalidate the
workspace/read queries. Reconnect with capped exponential backoff. TanStack
Query uses `refetchInterval: connected ? false : 5_000` and
`refetchOnWindowFocus: true`. Cleanup closes sockets and timers.

- [ ] **Step 5: Implement signed XHR upload**

```typescript
export async function putSignedFile(
  url: string,
  file: File,
  onProgress: (percent: number) => void,
  signal: AbortSignal,
): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", file.type);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error("UPLOAD_FAILED")));
    xhr.onerror = () => reject(new Error("UPLOAD_FAILED"));
    signal.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(file);
  });
}
```

Create intent through `apiFetch`, PUT direct to the signed URL, then complete
through `apiFetch`. Do not add cookies or app authorization headers to the
signed PUT.

- [ ] **Step 6: Run web unit/static gates and commit**

```powershell
npm --workspace @jepret/web test -- src/lib/conversations.test.tsx src/lib/uploads.test.ts
npm --workspace @jepret/web run lint
npm --workspace @jepret/web run typecheck
git add apps/web/src/lib/api.ts apps/web/src/lib/bookings.ts apps/web/src/lib/workspaces.ts apps/web/src/lib/conversations.ts apps/web/src/lib/uploads.ts apps/web/src/lib/deliverables.ts apps/web/src/lib/conversations.test.tsx apps/web/src/lib/uploads.test.ts
git commit -m "feat(web): add booking workspace clients"
```

## Task 11: Build the accessible mobile booking workspace and update entry points

**Files:**

- Create: `apps/web/src/components/workspace/workspace-header.tsx`
- Create: `apps/web/src/components/workspace/conversation-panel.tsx`
- Create: `apps/web/src/components/workspace/deliverables-panel.tsx`
- Create: `apps/web/src/components/workspace/upload-field.tsx`
- Create: `apps/web/src/app/booking/[id]/page.tsx`
- Create: `apps/web/src/app/booking/[id]/page.test.tsx`
- Modify: `apps/web/src/app/booking/page.tsx`
- Modify: `apps/web/src/app/booking/page.test.tsx`
- Modify: `apps/web/src/app/booking/masuk/page.tsx`
- Modify: `apps/web/src/app/booking/masuk/page.test.tsx`
- Modify: `apps/web/src/components/bookings/booking-card.tsx`
- Modify: `apps/web/src/app/booking/[id]/pembayaran/page.tsx`
- Modify: `apps/web/src/app/booking/[id]/pembayaran/page.test.tsx`

- [ ] **Step 1: Write failing workspace component tests**

Cover auth redirect, loading/error/empty, both roles, all status actions,
semantic tabs, 44px controls, message composer, attachment validation/progress,
external host display, private download, publish precondition, client accept
confirmation, terminal read-only, reconnect banner, and API errors in
Indonesian.

```tsx
expect(screen.getByRole("tab", { name: "Chat" })).toHaveAttribute("aria-selected", "true");
expect(screen.getByRole("button", { name: "Mulai sesi" })).toBeEnabled();
await user.click(screen.getByRole("tab", { name: "Hasil" }));
expect(screen.getByRole("tabpanel", { name: "Hasil" })).toBeVisible();
```

Entry-point tests assert **Buka ruang kerja** for confirmed/in-progress/
delivered/completed, no creator **Tandai selesai**, and no ordinary cancel after
work starts.

- [ ] **Step 2: Run focused tests to verify RED**

```powershell
npm --workspace @jepret/web test -- src/app/booking/[id]/page.test.tsx src/app/booking/page.test.tsx src/app/booking/masuk/page.test.tsx
```

Expected: FAIL because workspace UI/new behavior is absent.

- [ ] **Step 3: Implement workspace shell and accessible tabs**

Use a client page with `useMe` redirect and `useWorkspace`. Render an ordered
status progress list, role label, and buttons strictly from server role/status.
Implement tabs with `role=tablist`, arrow-key navigation, `aria-controls`,
`aria-selected`, and paired `tabpanel`. Keep composer near the bottom without
covering content or mobile navigation.

- [ ] **Step 4: Implement conversation and upload states**

Render messages as a semantic list with sender and Jakarta-local timestamp.
Use `aria-live="polite"` for new-message/reconnect status, not the whole message
list. Composer accepts text or one validated attachment, preserves the same
client UUID during retry, disables only the submitted action, and shows upload
progress/cancel/error/retry.

- [ ] **Step 5: Implement deliverable and lifecycle UI**

Creator `in_progress` sees file/link forms and delete controls. External links
show `new URL(url).host`. Private download first calls the authorized download
endpoint, then navigates to the returned short-lived URL. **Kirim hasil** is
disabled without deliverables. Client `delivered` sees **Terima hasil** with a
confirmation explaining that payment will be released.

- [ ] **Step 6: Update booking/payment entry points**

Add labels/classes for `in_progress` and `delivered`; include both in active
date selection but not ordinary cancellation. Replace creator completion with
workspace links. Payment page displays held/released state but exposes no
creator release action after Phase 6. Fetch the aggregate unread endpoint once
per list page and render an accessible unread badge on the matching booking
card without adding per-booking requests.

- [ ] **Step 7: Run full web gates and build**

```powershell
npm --workspace @jepret/web test
npm --workspace @jepret/web run lint
npm --workspace @jepret/web run typecheck
npm --workspace @jepret/web run build
```

Expected: all PASS with zero ESLint warnings.

- [ ] **Step 8: Commit**

```powershell
git add apps/web/src/components/workspace apps/web/src/app/booking/[id]/page.tsx apps/web/src/app/booking/[id]/page.test.tsx apps/web/src/app/booking/page.tsx apps/web/src/app/booking/page.test.tsx apps/web/src/app/booking/masuk/page.tsx apps/web/src/app/booking/masuk/page.test.tsx apps/web/src/components/bookings/booking-card.tsx apps/web/src/app/booking/[id]/pembayaran/page.tsx apps/web/src/app/booking/[id]/pembayaran/page.test.tsx
git commit -m "feat(web): add mobile booking workspace"
```

## Task 12: Prove the full flow, document Phase 6, review, and checkpoint GitHub

**Files:**

- Create: `apps/web/e2e/workspace.spec.ts`
- Modify: `apps/web/e2e/booking.spec.ts`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/testing.md`
- Modify: `docs/implementation-plan.md`

- [ ] **Step 1: Add the mobile acceptance E2E flow**

Use two isolated browser contexts so client and creator remain logged in
simultaneously. Reuse retry-safe available-date helpers, but include
`in_progress` and `delivered` in blocking statuses. Upload a small in-memory
PNG payload with Playwright `setInputFiles`, add an external HTTPS link, and
assert this sequence:

```typescript
await expect(clientPage.getByText("Terkonfirmasi")).toBeVisible();
await clientPage.getByLabel("Pesan").fill("Mohon foto keluarga juga.");
await clientPage.getByRole("button", { name: "Kirim pesan" }).click();
await expect(creatorPage.getByText("Mohon foto keluarga juga.")).toBeVisible();
await creatorPage.getByRole("button", { name: "Mulai sesi" }).click();
await creatorPage.getByRole("button", { name: "Kirim hasil" }).click();
await clientPage.getByRole("button", { name: "Terima hasil" }).click();
await expect(clientPage.getByText("Selesai")).toBeVisible();
await expect(clientPage.getByText("Pembayaran telah dilepas")).toBeVisible();
```

Also assert outsider access fails, terminal composer is absent, reload does not
duplicate the message, and private download URL expires/reissues through API.

- [ ] **Step 2: Run the new acceptance E2E and record the honest baseline**

```powershell
docker compose up -d --build
docker compose run --rm migrate
docker compose run --rm seed
npm --workspace @jepret/web run e2e -- workspace.spec.ts
```

Expected: record PASS or the exact failure. This acceptance test follows the
lower-level TDD tasks; do not manufacture or claim a RED result. Diagnose any
failure and add a focused regression before proceeding.

- [ ] **Step 3: Make E2E deterministic and retry-safe**

Use UUID message text, note, and object filename. Select active dates from the
authoritative incoming endpoint; handle `DATE_UNAVAILABLE` with the existing
bounded rejection/retry flow. Cleanup completed test bookings through
test-owned data or unique identities; never delete shared demo data. Run the
focused spec twice consecutively and once with two concurrent Playwright
processes.

- [ ] **Step 4: Update docs with actual behavior**

README must describe workspace, local MinIO signed upload endpoint, demo flow,
and Phase 1–6 status. Architecture documents REST-write/WebSocket-broadcast/
polling recovery and private storage trust boundaries. Testing lists exact
MinIO, focused API, web, and E2E commands. Do not add verification counts yet.

- [ ] **Step 5: Run the complete verification matrix**

```powershell
npm run format
npm run lint
npm run typecheck
uv run --project apps/api pytest apps/api/tests/test_storage_adapter.py apps/api/tests/test_rate_limit.py -q
uv run --project apps/api pytest apps/api/tests/test_bookings_api.py apps/api/tests/test_payments_api.py apps/api/tests/test_uploads_api.py apps/api/tests/test_conversations_api.py apps/api/tests/test_conversation_websocket.py apps/api/tests/test_deliverables_api.py apps/api/tests/test_workspace_lifecycle.py apps/api/tests/test_storage_integration.py -m integration -q
npm --workspace @jepret/web test
docker compose up -d --build
docker compose run --rm migrate
docker compose run --rm seed
npm --workspace @jepret/web run e2e -- workspace.spec.ts
npm --workspace @jepret/web run e2e -- workspace.spec.ts
npm --workspace @jepret/web run e2e
npm run verify
git diff --check
```

Expected: every command exits 0. Record exact pass counts and only real
warnings.

- [ ] **Step 6: Audit security and domain invariants**

Review the aggregate Phase 6 diff for secrets, object keys/URLs in API output,
unprotected routes, N+1 queries, unsafe external URL fetches, WebSocket Origin,
message body logging, row-lock order, provider release idempotency, migration
downgrade, contract drift, and unexpected files. Confirm the private bucket has
no anonymous policy.

- [ ] **Step 7: Commit the verified E2E**

```powershell
git add apps/web/e2e/workspace.spec.ts apps/web/e2e/booking.spec.ts
git commit -m "test(e2e): prove chat and delivery flow"
```

- [ ] **Step 8: Record truthful evidence and commit docs**

Append Phase 6 evidence with the current date and exact counts to
`docs/implementation-plan.md` only after Step 5. Then:

```powershell
git add README.md docs/architecture.md docs/testing.md docs/implementation-plan.md
git commit -m "docs: record phase 6 evidence"
```

- [ ] **Step 9: Request two-stage final review**

Dispatch a fresh spec reviewer against the approved design and this plan. Fix
all verified findings with TDD and re-review. Then dispatch a fresh code-quality
and security reviewer over the full Phase 6 range; fix and re-review until both
return APPROVED with no Critical, Important, or Minor findings.

- [ ] **Step 10: Push the verified checkpoint**

```powershell
git status --short --branch
git push origin codex/phase-5-payment
git status --short --branch
```

Expected: worktree clean and local branch synchronized with
`origin/codex/phase-5-payment`.

## Phase 6 completion report

Report:

- summary of chat, private uploads, deliverables, lifecycle, and payment release;
- every changed file grouped by domain;
- migration `20260816_0006` and downgrade result;
- exact unit, integration, Vitest, Playwright, build, and `npm run verify` results;
- authorization, transaction, concurrency, idempotency, and secret-review evidence;
- known limitations: single-instance broadcast, in-process rate limit, no antivirus, large video via external HTTPS link, admin access deferred to dispute;
- next recommended task: brainstorm Phase 7 reviews, disputes, and minimal admin workflow.
