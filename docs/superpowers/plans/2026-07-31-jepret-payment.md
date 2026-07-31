# Jepret Phase 5 Payment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menambahkan pembayaran penuh berbasis mock provider yang transaction-safe, idempoten, dan dapat dijalankan end-to-end dari booking diterima sampai payment released.

**Architecture:** Payment menjadi domain baru di modular monolith FastAPI. Route hanya menerjemahkan HTTP, payment service mengelola authorization, locking, state machine, dan transaksi, sedangkan `PaymentProvider` mengisolasi perilaku provider. Next.js memakai TanStack Query untuk halaman pembayaran mobile-first dan hanya menampilkan endpoint simulasi pada development/test.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Alembic, Pydantic, Pytest, Next.js App Router, TypeScript strict, TanStack Query, Vitest, Testing Library, Playwright.

---

## File map

**Create**

- `apps/api/migrations/versions/20260731_0005_payments.py` — perubahan schema booking, payment, event, dan unique date index.
- `apps/api/app/integrations/__init__.py` — package boundary integrasi.
- `apps/api/app/integrations/payments.py` — provider protocol, normalized event, dan mock provider.
- `apps/api/app/services/payments.py` — authorization, transaksi, fee, idempotency, refund, dan release.
- `apps/api/app/api/payments.py` — create/get payment dan webhook route.
- `apps/api/app/api/dev_payments.py` — endpoint simulasi yang hanya diregistrasikan non-production.
- `apps/api/tests/test_payment_provider.py` — unit test mock adapter.
- `apps/api/tests/test_payments_api.py` — integration test payment dan authorization.
- `apps/web/src/lib/payments.ts` — query keys dan payment mutations.
- `apps/web/src/app/booking/[id]/pembayaran/page.tsx` — halaman pembayaran.
- `apps/web/src/app/booking/[id]/pembayaran/page.test.tsx` — component tests halaman pembayaran.

**Modify**

- `packages/contracts/openapi.json` dan `packages/contracts/src/schema.d.ts` — selesaikan baseline booking lalu generate payment contract.
- `apps/api/app/db/models.py` — model dan relationships payment.
- `apps/api/app/api/schemas.py` — public payment schemas.
- `apps/api/app/services/bookings.py` — completion/cancellation yang sadar payment.
- `apps/api/app/main.py` — register payment routers dan conditional dev router.
- `apps/api/scripts/seed_demo.py` — payment demo idempoten.
- `apps/api/tests/integration/test_database.py` — assertions schema dan partial unique index.
- `apps/api/tests/test_bookings_api.py` — state booking baru dan regression cancellation.
- `apps/web/src/lib/api.ts` — booking/payment TypeScript types.
- `apps/web/src/lib/bookings.ts` — labels dan active states baru.
- `apps/web/src/components/bookings/booking-card.tsx` — badges status payment-era.
- `apps/web/src/app/booking/page.tsx` dan `page.test.tsx` — CTA pembayaran klien.
- `apps/web/src/app/booking/masuk/page.tsx` dan `page.test.tsx` — aksi kreator hanya pada confirmed.
- `apps/web/e2e/booking.spec.ts` — transaksi lengkap.
- `.env.example`, `docker-compose.yml`, `README.md`, `docs/implementation-plan.md`, dan `docs/testing.md` — mode sandbox dan bukti Phase 5.

## Task 1: Reconcile the Phase 4 contract baseline

**Files:**

- Modify: `packages/contracts/openapi.json`
- Modify: `packages/contracts/src/schema.d.ts`

- [ ] **Step 1: Verify the existing dirty files contain only the booking contract**

Run:

```powershell
git diff -- packages/contracts/openapi.json packages/contracts/src/schema.d.ts
```

Expected: additions are limited to `BookingOut`, booking envelopes, and the
eight booking-prefixed operations already implemented in Phase 4. Stop and
investigate if auth, creator, or unrelated schemas disappear.

- [ ] **Step 2: Verify deterministic contract generation**

Run:

```powershell
npm run contracts:check
```

Expected: PASS and no additional contract diff.

- [ ] **Step 3: Commit the Phase 4 generated baseline separately**

```powershell
git add packages/contracts/openapi.json packages/contracts/src/schema.d.ts
git commit -m "chore(contracts): sync booking API contract"
```

This prevents pre-existing Phase 4 output from being mixed into payment commits.

## Task 2: Add the payment schema and ORM models

**Files:**

- Create: `apps/api/migrations/versions/20260731_0005_payments.py`
- Modify: `apps/api/app/db/models.py`
- Modify: `apps/api/tests/integration/test_database.py`

- [ ] **Step 1: Write failing schema assertions**

Append this integration test:

```python
@pytest.mark.integration
async def test_payment_schema_and_active_date_index() -> None:
    async with fresh_connection() as connection:
        payment_columns = set(
            await connection.scalars(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'payments'
                    """
                )
            )
        )
        event_constraint = await connection.scalar(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'uq_payment_event_provider_id'
                """
            )
        )
        date_index = await connection.scalar(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE indexname = 'uq_bookings_active_date'
                """
            )
        )

    assert {
        "booking_id",
        "provider",
        "provider_reference",
        "idempotency_key",
        "amount_idr",
        "platform_fee_idr",
        "creator_net_idr",
        "status",
        "raw_metadata",
    } <= payment_columns
    assert event_constraint is not None
    assert "provider_event_id" in event_constraint
    assert date_index is not None
    assert "awaiting_payment" in date_index
    assert "confirmed" in date_index
```

- [ ] **Step 2: Run the test and verify it fails before the migration**

Run:

```powershell
uv run --project apps/api pytest apps/api/tests/integration/test_database.py::test_payment_schema_and_active_date_index -m integration -q
```

Expected: FAIL because `payments` and `uq_bookings_active_date` do not exist.

- [ ] **Step 3: Create migration `20260731_0005`**

Implement `upgrade()` with these exact invariants:

```python
"""Add sandbox payments and payment events."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260731_0005"
down_revision = "20260721_0004"
branch_labels = None
depends_on = None

BOOKING_STATUS = (
    "status IN ('requested', 'accepted', 'awaiting_payment', 'confirmed', "
    "'rejected', 'completed', 'cancelled')"
)
PAYMENT_STATUS = (
    "status IN ('pending', 'paid', 'held', 'released', 'refunded', 'failed', 'expired')"
)


def upgrade() -> None:
    op.drop_index("uq_bookings_accepted_date", table_name="bookings")
    op.drop_constraint("ck_booking_status_valid", "bookings", type_="check")
    op.create_check_constraint("ck_booking_status_valid", "bookings", BOOKING_STATUS)
    op.create_index(
        "uq_bookings_active_date",
        "bookings",
        ["creator_profile_id", "event_date"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('accepted', 'awaiting_payment', 'confirmed')"
        ),
    )
    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "booking_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_reference", sa.String(100), nullable=True, unique=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("amount_idr", sa.BigInteger(), nullable=False),
        sa.Column("platform_fee_idr", sa.BigInteger(), nullable=False),
        sa.Column("creator_net_idr", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(PAYMENT_STATUS, name="ck_payment_status_valid"),
        sa.CheckConstraint("amount_idr > 0", name="ck_payment_amount_positive"),
        sa.CheckConstraint(
            "platform_fee_idr >= 0 AND creator_net_idr >= 0",
            name="ck_payment_parts_non_negative",
        ),
        sa.CheckConstraint(
            "amount_idr = platform_fee_idr + creator_net_idr",
            name="ck_payment_amount_parts",
        ),
    )
    op.create_table(
        "payment_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "payment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_event_id", sa.String(150), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_event_provider_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("payment_events")
    op.drop_table("payments")
    op.drop_index("uq_bookings_active_date", table_name="bookings")
    op.drop_constraint("ck_booking_status_valid", "bookings", type_="check")
    op.execute(
        "UPDATE bookings SET status = 'accepted' "
        "WHERE status IN ('awaiting_payment', 'confirmed')"
    )
    op.create_check_constraint(
        "ck_booking_status_valid",
        "bookings",
        "status IN ('requested', 'accepted', 'rejected', 'completed', 'cancelled')",
    )
    op.create_index(
        "uq_bookings_accepted_date",
        "bookings",
        ["creator_profile_id", "event_date"],
        unique=True,
        postgresql_where=sa.text("status = 'accepted'"),
    )
```

Format long Alembic column calls with Ruff before committing.

- [ ] **Step 4: Add ORM models**

Add `JSON`, `UniqueConstraint`, and these constants/classes to
`apps/api/app/db/models.py`; update the booking constraint and date index to
match the migration:

```python
PAYMENT_STATUSES = (
    "pending",
    "paid",
    "held",
    "released",
    "refunded",
    "failed",
    "expired",
)


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'paid', 'held', 'released', 'refunded', 'failed', 'expired')",
            name="ck_payment_status_valid",
        ),
        CheckConstraint("amount_idr > 0", name="ck_payment_amount_positive"),
        CheckConstraint(
            "platform_fee_idr >= 0 AND creator_net_idr >= 0",
            name="ck_payment_parts_non_negative",
        ),
        CheckConstraint(
            "amount_idr = platform_fee_idr + creator_net_idr",
            name="ck_payment_amount_parts",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(100), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    amount_idr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    platform_fee_idr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_net_idr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON)

    booking: Mapped["Booking"] = relationship(back_populates="payment")
    events: Mapped[list["PaymentEvent"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_event_provider_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(150), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    payment: Mapped[Payment] = relationship(back_populates="events")
```

Add this one-to-one relationship to `Booking`:

```python
payment: Mapped["Payment | None"] = relationship(
    back_populates="booking", cascade="all, delete-orphan", uselist=False
)
```

- [ ] **Step 5: Apply migration and run schema test**

Run:

```powershell
uv run --project apps/api alembic upgrade head
uv run --project apps/api pytest apps/api/tests/integration/test_database.py -m integration -q
```

Expected: all database integration tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/api/migrations/versions/20260731_0005_payments.py apps/api/app/db/models.py apps/api/tests/integration/test_database.py
git commit -m "feat(api): add payment schema"
```

## Task 3: Implement the provider boundary

**Files:**

- Create: `apps/api/app/integrations/__init__.py`
- Create: `apps/api/app/integrations/payments.py`
- Create: `apps/api/tests/test_payment_provider.py`

- [ ] **Step 1: Write failing provider tests**

```python
import uuid

import pytest

from app.integrations.payments import MockPaymentProvider, PaymentEvent


@pytest.mark.asyncio
async def test_mock_provider_creates_deterministic_reference() -> None:
    provider = MockPaymentProvider()
    payment_id = uuid.uuid4()
    first = await provider.create_payment(payment_id=payment_id, amount_idr=1_500_000)
    second = await provider.create_payment(payment_id=payment_id, amount_idr=1_500_000)
    assert first == second == f"mock-{payment_id}"
    assert await provider.get_payment_status(first) == "pending"


@pytest.mark.asyncio
async def test_mock_provider_normalizes_paid_refund_and_release() -> None:
    provider = MockPaymentProvider()
    payment_id = uuid.uuid4()
    paid = await provider.simulate_paid(payment_id)
    refunded = await provider.refund_payment(payment_id)
    released = await provider.release_payment(payment_id)
    assert paid == PaymentEvent(f"mock-paid-{payment_id}", "paid")
    assert refunded.event_type == "refunded"
    assert released.event_type == "released"
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
uv run --project apps/api pytest apps/api/tests/test_payment_provider.py -q
```

Expected: FAIL because `app.integrations.payments` does not exist.

- [ ] **Step 3: Implement the protocol and mock provider**

```python
import uuid
from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True)
class PaymentEvent:
    provider_event_id: str
    event_type: str


class PaymentProvider(Protocol):
    name: str

    async def create_payment(self, *, payment_id: uuid.UUID, amount_idr: int) -> str:
        raise NotImplementedError

    async def get_payment_status(self, provider_reference: str) -> str:
        raise NotImplementedError

    async def handle_webhook(
        self, *, payload: Mapping[str, object], headers: Mapping[str, str]
    ) -> PaymentEvent:
        raise NotImplementedError

    async def refund_payment(self, payment_id: uuid.UUID) -> PaymentEvent:
        raise NotImplementedError

    async def release_payment(self, payment_id: uuid.UUID) -> PaymentEvent:
        raise NotImplementedError


class MockPaymentProvider:
    name = "mock"

    async def create_payment(self, *, payment_id: uuid.UUID, amount_idr: int) -> str:
        if amount_idr <= 0:
            raise ValueError("amount_idr must be positive")
        return f"mock-{payment_id}"

    async def get_payment_status(self, provider_reference: str) -> str:
        if not provider_reference.startswith("mock-"):
            raise ValueError("invalid mock provider reference")
        return "pending"

    async def handle_webhook(
        self, *, payload: Mapping[str, object], headers: Mapping[str, str]
    ) -> PaymentEvent:
        event_id = str(payload.get("event_id", ""))
        event_type = str(payload.get("event_type", ""))
        if not event_id or event_type not in {"paid", "failed"}:
            raise ValueError("invalid mock webhook")
        return PaymentEvent(event_id, event_type)

    async def simulate_paid(self, payment_id: uuid.UUID) -> PaymentEvent:
        return PaymentEvent(f"mock-paid-{payment_id}", "paid")

    async def refund_payment(self, payment_id: uuid.UUID) -> PaymentEvent:
        return PaymentEvent(f"mock-refunded-{payment_id}", "refunded")

    async def release_payment(self, payment_id: uuid.UUID) -> PaymentEvent:
        return PaymentEvent(f"mock-released-{payment_id}", "released")
```

- [ ] **Step 4: Run provider tests**

Run:

```powershell
uv run --project apps/api pytest apps/api/tests/test_payment_provider.py -q
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/integrations apps/api/tests/test_payment_provider.py
git commit -m "feat(api): add mock payment provider"
```

## Task 4: Build payment service and API with idempotency

**Files:**

- Create: `apps/api/app/services/payments.py`
- Create: `apps/api/app/api/payments.py`
- Create: `apps/api/app/api/dev_payments.py`
- Create: `apps/api/tests/test_payments_api.py`
- Modify: `apps/api/app/api/schemas.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Write integration tests first**

Create tests that use the existing register/login/creator setup pattern from
`test_bookings_api.py`. The central happy-path assertion must be:

```python
created = client.post(
    f"/api/v1/bookings/{booking_id}/payments",
    headers={"Idempotency-Key": key},
)
retried = client.post(
    f"/api/v1/bookings/{booking_id}/payments",
    headers={"Idempotency-Key": key},
)
paid = client.post(f"/api/v1/dev/payments/{created.json()['data']['id']}/simulate-paid")
booking = client.get(f"/api/v1/bookings/{booking_id}")

assert created.status_code == 201
assert retried.status_code == 200
assert retried.json()["data"]["id"] == created.json()["data"]["id"]
assert created.json()["data"]["amount_idr"] == 1_500_000
assert created.json()["data"]["platform_fee_idr"] == 150_000
assert created.json()["data"]["creator_net_idr"] == 1_350_000
assert paid.json()["data"]["status"] == "held"
assert booking.json()["data"]["status"] == "confirmed"
```

Add separate tests for:

```python
assert missing_key.json()["error"]["code"] == "INVALID_IDEMPOTENCY_KEY"
assert wrong_owner.status_code == 404
assert create_before_accept.json()["error"]["code"] == "PAYMENT_NOT_ALLOWED"
assert duplicate_key_other_booking.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
assert replay_paid.json()["data"]["status"] == "held"
```

Use unique users and fixture cleanup; do not depend on seeded rows.

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
uv run --project apps/api pytest apps/api/tests/test_payments_api.py -m integration -q
```

Expected: FAIL with missing payment routes.

- [ ] **Step 3: Add public schemas**

Add:

```python
class PaymentOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    provider: str
    amount_idr: int
    platform_fee_idr: int
    creator_net_idr: int
    status: str
    paid_at: datetime | None
    held_at: datetime | None
    released_at: datetime | None
    refunded_at: datetime | None
    created_at: datetime


class PaymentEnvelope(BaseModel):
    data: PaymentOut
```

- [ ] **Step 4: Implement the payment service**

The service must expose six typed operations: `create_payment()` returns
`tuple[Payment, bool]` where the boolean marks a new row; `get_for_user()`
returns the related payment; `apply_provider_event()` applies a normalized
event; `simulate_paid()` and `release()` authorize their respective actors; and
`expire_or_refund_for_cancellation()` mutates the locked payment without
committing.

Implement fee calculation exactly:

```python
amount = booking.quoted_price_idr
platform_fee = amount * 10 // 100
creator_net = amount - platform_fee
```

For event application, map normalized events atomically:

```python
if event.event_type == "paid":
    require(payment.status == "pending" and booking.status == "awaiting_payment")
    payment.status = "held"
    payment.paid_at = now
    payment.held_at = now
    booking.status = "confirmed"
elif event.event_type == "failed":
    require(payment.status == "pending")
    payment.status = "failed"
elif event.event_type == "refunded":
    require(payment.status == "held")
    payment.status = "refunded"
    payment.refunded_at = now
elif event.event_type == "released":
    require(payment.status == "held" and booking.status == "completed")
    payment.status = "released"
    payment.released_at = now
else:
    raise DomainError(
        "INVALID_PAYMENT_TRANSITION",
        "Status pembayaran tidak memungkinkan aksi ini.",
        status_code=409,
    )
```

Before mapping, query `PaymentEvent` by `(provider, provider_event_id)` and
return the current payment on replay. Lock booking and payment rows. Commit only
after adding the event row and all state changes.

Convert `IntegrityError` for reused idempotency keys to
`IDEMPOTENCY_CONFLICT`; do not return database details.

- [ ] **Step 5: Add HTTP routes**

`payments.py` must:

- validate `Idempotency-Key` as a UUID-shaped string of at most 100 characters;
- return 201 for a newly created payment and 200 for an existing one;
- expose GET to both related parties;
- parse mock webhook only outside production;
- serialize through a single `payment_out()` helper exported by `payments.py`
  and reused by `dev_payments.py`.

`dev_payments.py` must expose:

```python
@router.post("/{payment_id}/simulate-paid", response_model=PaymentEnvelope)
async def simulate_paid(
    payment_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> PaymentEnvelope:
    payment = await payment_service.simulate_paid(
        db, payment_id=payment_id, user=user
    )
    return PaymentEnvelope(data=payment_out(payment))


@router.post("/{payment_id}/simulate-release", response_model=PaymentEnvelope)
async def simulate_release(
    payment_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> PaymentEnvelope:
    payment = await payment_service.release(db, payment_id=payment_id, user=user)
    return PaymentEnvelope(data=payment_out(payment))
```

In `create_app()`, always register `payments_router` and only register
`dev_payments_router` when:

```python
if get_settings().environment is not Environment.PRODUCTION:
    app.include_router(dev_payments_router)
```

- [ ] **Step 6: Run payment API tests**

Run:

```powershell
uv run --project apps/api pytest apps/api/tests/test_payments_api.py -m integration -q
```

Expected: all payment integration tests PASS.

- [ ] **Step 7: Run authorization and API regression tests**

Run:

```powershell
uv run --project apps/api pytest apps/api/tests -m integration -q
```

Expected: payment tests pass; the old accepted-to-completed booking test may
still fail until Task 5 and is not ignored.

- [ ] **Step 8: Commit**

```powershell
git add apps/api/app/api/payments.py apps/api/app/api/dev_payments.py apps/api/app/api/schemas.py apps/api/app/integrations/payments.py apps/api/app/services/payments.py apps/api/app/main.py apps/api/tests/test_payments_api.py
git commit -m "feat(api): add idempotent payment endpoints"
```

## Task 5: Couple booking cancellation and completion to payment

**Files:**

- Modify: `apps/api/app/services/bookings.py`
- Modify: `apps/api/tests/test_bookings_api.py`
- Modify: `apps/api/tests/test_payments_api.py`

- [ ] **Step 1: Replace the old completion expectation with payment-era tests**

Change the existing accepted completion test to assert:

```python
complete_before_payment = client.post(f"/api/v1/bookings/{booking_id}/complete")
assert complete_before_payment.status_code == 409
assert complete_before_payment.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
```

Then create and hold the payment as the client, log back in as creator, and
assert completion succeeds from `confirmed`.

Add cancellation assertions:

```python
cancelled = client.post(f"/api/v1/bookings/{booking_id}/cancel")
payment = client.get(f"/api/v1/bookings/{booking_id}/payments")
assert cancelled.json()["data"]["status"] == "cancelled"
assert payment.json()["data"]["status"] == "refunded"
```

Add a pending-payment cancellation case expecting `expired`.

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```powershell
uv run --project apps/api pytest apps/api/tests/test_bookings_api.py apps/api/tests/test_payments_api.py -m integration -q
```

Expected: FAIL because booking service still completes `accepted` and does not
transition payment during cancellation.

- [ ] **Step 3: Update booking rules**

Use:

```python
ACTIVE_STATUSES = frozenset(
    {"requested", "accepted", "awaiting_payment", "confirmed"}
)
```

Require `confirmed` in `complete_booking()`. In `cancel_booking()`, after
authorization and locking but before assigning `cancelled`, call:

```python
await payment_service.expire_or_refund_for_cancellation(db, booking=booking)
booking.status = "cancelled"
booking.cancelled_at = datetime.now(UTC)
await db.commit()
```

`expire_or_refund_for_cancellation()` must only `flush()`, not commit, so refund
state and booking cancellation are one transaction. Provider failure must raise
before either state is committed.

- [ ] **Step 4: Preserve the active-date invariant**

Add an integration test that accepts booking A, moves it to `confirmed`, then
tries to accept booking B for the same creator/date. Assert 409
`DATE_UNAVAILABLE`. This proves payment transitions do not free the date.

- [ ] **Step 5: Run booking and payment tests**

Run:

```powershell
uv run --project apps/api pytest apps/api/tests/test_bookings_api.py apps/api/tests/test_payments_api.py -m integration -q
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/api/app/services/bookings.py apps/api/tests/test_bookings_api.py apps/api/tests/test_payments_api.py
git commit -m "feat(api): integrate booking and payment states"
```

## Task 6: Seed payments and regenerate contracts

**Files:**

- Modify: `apps/api/scripts/seed_demo.py`
- Modify: `packages/contracts/openapi.json`
- Modify: `packages/contracts/src/schema.d.ts`

- [ ] **Step 1: Add idempotent payment seed**

Extend demo bookings to cover `awaiting_payment`, `confirmed`, and `completed`.
After bookings are flushed, create payments only when `booking.payment` is
absent:

```python
amount = booking.quoted_price_idr
fee = amount * 10 // 100
payment = Payment(
    booking_id=booking.id,
    provider="mock",
    provider_reference=f"mock-{booking.id}",
    idempotency_key=f"seed-{booking.id}",
    amount_idr=amount,
    platform_fee_idr=fee,
    creator_net_idr=amount - fee,
    status=payment_status,
    paid_at=paid_at,
    held_at=held_at,
    released_at=released_at,
)
db.add(payment)
```

Use fixed UTC timestamps derived from `BASE_REVIEWED_AT`, not `now()`, for
deterministic seed status timestamps.

- [ ] **Step 2: Run seed twice**

Run:

```powershell
uv run --project apps/api python apps/api/scripts/seed_demo.py
uv run --project apps/api python apps/api/scripts/seed_demo.py
```

Expected: second run reports existing data and creates no duplicate payment.

- [ ] **Step 3: Generate and verify contracts**

Run:

```powershell
npm run contracts:generate
npm run contracts:check
```

Expected: OpenAPI contains payment schemas and five payment operations; check
PASS.

- [ ] **Step 4: Commit**

```powershell
git add apps/api/scripts/seed_demo.py packages/contracts/openapi.json packages/contracts/src/schema.d.ts
git commit -m "feat(api): seed payments and publish contracts"
```

## Task 7: Add frontend payment types and booking CTAs

**Files:**

- Create: `apps/web/src/lib/payments.ts`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/lib/bookings.ts`
- Modify: `apps/web/src/components/bookings/booking-card.tsx`
- Modify: `apps/web/src/app/booking/page.tsx`
- Modify: `apps/web/src/app/booking/page.test.tsx`
- Modify: `apps/web/src/app/booking/masuk/page.tsx`
- Modify: `apps/web/src/app/booking/masuk/page.test.tsx`

- [ ] **Step 1: Write failing client and creator UI tests**

Client test:

```tsx
it("links accepted bookings to payment", async () => {
  stubFetch([booking("b1", "accepted")]);
  renderPage();
  expect(
    await screen.findByRole("link", { name: "Bayar sekarang" }),
  ).toHaveAttribute("href", "/booking/b1/pembayaran");
});
```

Creator tests:

```tsx
it("only completes confirmed bookings", async () => {
  stubFetch(incoming("confirmed"));
  renderPage();
  expect(
    await screen.findByRole("button", { name: "Tandai selesai" }),
  ).toBeVisible();
});

it("does not complete a booking that is awaiting payment", async () => {
  stubFetch(incoming("awaiting_payment"));
  renderPage();
  expect(await screen.findByText("Menunggu pembayaran")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Tandai selesai" }),
  ).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
npm --workspace @jepret/web test -- src/app/booking/page.test.tsx src/app/booking/masuk/page.test.tsx
```

Expected: FAIL because payment statuses and CTA do not exist.

- [ ] **Step 3: Add strict TypeScript types and hooks**

Extend `BookingStatus` with `awaiting_payment` and `confirmed`. Add:

```typescript
export type PaymentStatus =
  | "pending"
  | "paid"
  | "held"
  | "released"
  | "refunded"
  | "failed"
  | "expired";

export interface Payment {
  id: string;
  booking_id: string;
  provider: "mock";
  amount_idr: number;
  platform_fee_idr: number;
  creator_net_idr: number;
  status: PaymentStatus;
  paid_at: string | null;
  held_at: string | null;
  released_at: string | null;
  refunded_at: string | null;
  created_at: string;
}
```

Implement hooks:

```typescript
export const paymentKey = (bookingId: string) =>
  ["payments", bookingId] as const;

export function usePayment(bookingId: string) {
  return useQuery({
    queryKey: paymentKey(bookingId),
    queryFn: () => apiFetch<Payment>(`/bookings/${bookingId}/payments`),
    retry: false,
  });
}

export function useCreatePayment(bookingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (idempotencyKey: string) =>
      apiFetch<Payment>(`/bookings/${bookingId}/payments`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
      }),
    onSuccess: (payment) => {
      queryClient.setQueryData(paymentKey(bookingId), payment);
      queryClient.invalidateQueries({ queryKey: BOOKINGS_KEY });
    },
  });
}
```

Add equivalent `useSimulatePaid(paymentId, bookingId)` and
`useSimulateRelease(paymentId, bookingId)` mutations.

- [ ] **Step 4: Update booking labels and UI**

Use labels:

```typescript
awaiting_payment: "Menunggu pembayaran",
confirmed: "Terkonfirmasi",
```

Allow cancellation for `requested`, `accepted`, `awaiting_payment`, and
`confirmed`. Add distinct badge colors for the new statuses.

In the client list, render:

```tsx
{booking.status === "accepted" ? (
  <Link href={`/booking/${booking.id}/pembayaran`} className={primaryActionClass}>
    Bayar sekarang
  </Link>
) : booking.status === "awaiting_payment" ||
  booking.status === "confirmed" ? (
  <Link href={`/booking/${booking.id}/pembayaran`} className={secondaryActionClass}>
    Lihat pembayaran
  </Link>
) : null}
```

Creator completion must render only for `confirmed`.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
npm --workspace @jepret/web test -- src/app/booking/page.test.tsx src/app/booking/masuk/page.test.tsx
```

Expected: all focused component tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/src/lib/api.ts apps/web/src/lib/payments.ts apps/web/src/lib/bookings.ts apps/web/src/components/bookings/booking-card.tsx apps/web/src/app/booking/page.tsx apps/web/src/app/booking/page.test.tsx apps/web/src/app/booking/masuk/page.tsx apps/web/src/app/booking/masuk/page.test.tsx
git commit -m "feat(web): add payment states to bookings"
```

## Task 8: Build the mobile payment page

**Files:**

- Create: `apps/web/src/app/booking/[id]/pembayaran/page.tsx`
- Create: `apps/web/src/app/booking/[id]/pembayaran/page.test.tsx`

- [ ] **Step 1: Write page tests**

Test these states with mocked fetch responses:

```tsx
it("creates a payment with one stable idempotency key", async () => {
  renderPage("b1", acceptedBooking);
  await userEvent.click(
    await screen.findByRole("button", { name: "Buat pembayaran" }),
  );
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/bookings/b1/payments",
    expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }),
    }),
  );
});

it("simulates a successful pending payment", async () => {
  renderPage("b1", acceptedBooking, pendingPayment);
  await userEvent.click(
    await screen.findByRole("button", {
      name: "Simulasikan pembayaran berhasil",
    }),
  );
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/dev/payments/p1/simulate-paid",
    expect.objectContaining({ method: "POST" }),
  );
});

it.each([
  ["held", "Dana tercatat aman"],
  ["refunded", "Pembayaran dikembalikan"],
  ["released", "Pembayaran telah dilepas"],
  ["failed", "Pembayaran gagal"],
  ["expired", "Pembayaran kedaluwarsa"],
])("renders %s status", async (status, label) => {
  renderPage("b1", acceptedBooking, payment(status));
  expect(await screen.findByText(label)).toBeVisible();
});
```

Also assert unauthenticated redirect, loading skeleton, 404/no-payment state,
generic error alert, and retry button.

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
npm --workspace @jepret/web test -- "src/app/booking/[id]/pembayaran/page.test.tsx"
```

Expected: FAIL because the page does not exist.

- [ ] **Step 3: Implement the page**

The page must:

- use `useParams<{ id: string }>()`;
- fetch the booking first;
- treat payment GET 404 as “belum dibuat”, not a generic failure;
- generate the idempotency key once with `useState(() => crypto.randomUUID())`;
- show total using `formatIdr`;
- clearly label “Pembayaran simulasi — tidak ada dana nyata yang diproses”;
- disable mutation buttons while pending;
- invalidate booking and payment queries on every successful mutation;
- present errors in an element with `role="alert"`;
- retain `AppHeader` and `BottomNavigation`;
- keep actions at least 44px high and keyboard accessible.

Use this status copy:

```typescript
const PAYMENT_COPY: Record<PaymentStatus, string> = {
  pending: "Menunggu pembayaran",
  paid: "Pembayaran diterima",
  held: "Dana tercatat aman",
  released: "Pembayaran telah dilepas",
  refunded: "Pembayaran dikembalikan",
  failed: "Pembayaran gagal",
  expired: "Pembayaran kedaluwarsa",
};
```

- [ ] **Step 4: Run page and frontend suites**

Run:

```powershell
npm --workspace @jepret/web test -- "src/app/booking/[id]/pembayaran/page.test.tsx"
npm --workspace @jepret/web test
npm --workspace @jepret/web run typecheck
```

Expected: all Vitest tests and TypeScript checks PASS.

- [ ] **Step 5: Commit**

```powershell
git add "apps/web/src/app/booking/[id]/pembayaran/page.tsx" "apps/web/src/app/booking/[id]/pembayaran/page.test.tsx"
git commit -m "feat(web): add sandbox payment page"
```

## Task 9: Complete E2E, configuration, docs, and verification

**Files:**

- Modify: `apps/web/e2e/booking.spec.ts`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `docs/implementation-plan.md`
- Modify: `docs/testing.md`

- [ ] **Step 1: Extend the booking E2E flow**

After creator acceptance, add:

```typescript
await page.goto("/profil");
await page.getByRole("button", { name: "Keluar" }).click();
await login(page, CLIENT);
await page.goto("/booking");
await card.getByRole("link", { name: "Bayar sekarang" }).click();
await page.getByRole("button", { name: "Buat pembayaran" }).click();
await page
  .getByRole("button", { name: "Simulasikan pembayaran berhasil" })
  .click();
await expect(page.getByText("Dana tercatat aman")).toBeVisible();
```

Then log in as creator, mark the booking complete, open its payment page, run
**Simulasikan pencairan**, and assert **Pembayaran telah dilepas**.

Add a separate E2E case that pays another booking, cancels it, and observes
**Pembayaran dikembalikan**.

- [ ] **Step 2: Document environment behavior**

Add:

```dotenv
# Mock payment and /api/v1/dev/payments/* are unavailable in production.
JEPRET_ENVIRONMENT=development
```

Keep Compose explicitly on development. README must replace stale Phase 1
claims with:

- Phase 1–5 status;
- local payment sandbox walkthrough;
- warning that held/released are simulated business states;
- current auth/payment security caveats;
- migration head `20260731_0005`.

Update `docs/testing.md` with the focused payment commands from this plan.

- [ ] **Step 3: Run formatting**

Run:

```powershell
npm run format
```

Expected: Ruff and Prettier complete successfully.

- [ ] **Step 4: Run backend and frontend focused tests**

Run:

```powershell
uv run --project apps/api pytest apps/api/tests/test_payment_provider.py -q
uv run --project apps/api pytest apps/api/tests/test_bookings_api.py apps/api/tests/test_payments_api.py -m integration -q
npm --workspace @jepret/web test
```

Expected: all focused suites PASS.

- [ ] **Step 5: Run E2E**

Start the local stack, migrate, and seed:

```powershell
docker compose up -d --build
docker compose run --rm migrate
docker compose run --rm seed
npm --workspace @jepret/web run e2e
```

Expected: foundation, auth, marketplace, booking, and payment E2E tests PASS.

- [ ] **Step 6: Run the repository quality gate**

Run:

```powershell
npm run verify
```

Expected: format check, lint, type-check, tests, contract check, build, and
Compose config all PASS.

- [ ] **Step 7: Review security and diff**

Run:

```powershell
git diff --check
git diff --stat
git grep -n -I -E "(api[_-]?key|secret|password|token)" -- . ":!package-lock.json" ":!apps/api/uv.lock"
```

Confirm:

- no secret or raw payment metadata is exposed;
- dev endpoints are absent in production;
- every mutation performs backend authorization;
- booking/payment state changes share one transaction;
- contract files match the API;
- only intended docs mark Phase 5 complete.

- [ ] **Step 8: Record evidence and commit**

Add actual test counts and the verification date to
`docs/implementation-plan.md`; only then check Phase 5:

```markdown
- [x] Phase 5 — Payment
```

Commit:

```powershell
git add .env.example docker-compose.yml README.md docs/implementation-plan.md docs/testing.md apps/web/e2e/booking.spec.ts
git commit -m "test(e2e): cover payment flow; docs: record phase 5"
```

- [ ] **Step 9: Final status check**

Run:

```powershell
git status --short
git log -8 --oneline
```

Expected: clean worktree and a reviewable sequence of focused Phase 5 commits.
