import uuid

from fastapi import APIRouter, Header, Request, Response, status
from pydantic import ValidationError

from app.api.deps import CurrentUser, DbSession
from app.api.schemas import MockPaymentWebhookRequest, PaymentEnvelope, PaymentOut
from app.core.config import Environment, get_settings
from app.core.errors import DomainError
from app.db.models import Payment
from app.services import payments as payment_service

router = APIRouter(tags=["payments"])


def _payment_out(payment: Payment) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        booking_id=payment.booking_id,
        provider=payment.provider,
        amount_idr=payment.amount_idr,
        platform_fee_idr=payment.platform_fee_idr,
        creator_net_idr=payment.creator_net_idr,
        status=payment.status,
        paid_at=payment.paid_at,
        held_at=payment.held_at,
        released_at=payment.released_at,
        refunded_at=payment.refunded_at,
        created_at=payment.created_at,
    )


def _validate_idempotency_key(value: str | None) -> str:
    if value is None or len(value) > 100:
        raise DomainError(
            "INVALID_IDEMPOTENCY_KEY",
            "Idempotency-Key harus berupa UUID kanonis.",
            status_code=422,
        )
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise DomainError(
            "INVALID_IDEMPOTENCY_KEY",
            "Idempotency-Key harus berupa UUID kanonis.",
            status_code=422,
        ) from exc
    if value != str(parsed):
        raise DomainError(
            "INVALID_IDEMPOTENCY_KEY",
            "Idempotency-Key harus berupa UUID kanonis.",
            status_code=422,
        )
    return value


@router.post(
    "/api/v1/bookings/{booking_id}/payments",
    response_model=PaymentEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    booking_id: uuid.UUID,
    response: Response,
    user: CurrentUser,
    db: DbSession,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PaymentEnvelope:
    payment, created = await payment_service.create_payment(
        db,
        booking_id=booking_id,
        user=user,
        idempotency_key=_validate_idempotency_key(idempotency_key),
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return PaymentEnvelope(data=_payment_out(payment))


@router.get(
    "/api/v1/bookings/{booking_id}/payments",
    response_model=PaymentEnvelope,
)
async def get_payment(booking_id: uuid.UUID, user: CurrentUser, db: DbSession) -> PaymentEnvelope:
    payment = await payment_service.get_for_booking(db, booking_id=booking_id, user=user)
    return PaymentEnvelope(data=_payment_out(payment))


@router.post(
    "/api/v1/payments/webhooks/{provider}",
    response_model=PaymentEnvelope,
)
async def payment_webhook(
    provider: str,
    request: Request,
    db: DbSession,
) -> PaymentEnvelope:
    if provider != payment_service.PROVIDER.name:
        raise DomainError("NOT_FOUND", "Provider pembayaran tidak ditemukan.", 404)
    if get_settings().environment == Environment.PRODUCTION:
        raise DomainError(
            "DEV_ENDPOINT_DISABLED",
            "Endpoint pengembangan tidak tersedia.",
            404,
        )
    try:
        payload = MockPaymentWebhookRequest.model_validate(await request.json())
    except (ValueError, ValidationError) as exc:
        raise DomainError(
            "REQUEST_VALIDATION_FAILED",
            "Data permintaan tidak valid.",
            422,
        ) from exc
    try:
        event = await payment_service.PROVIDER.handle_webhook(
            payload=payload.model_dump(exclude={"payment_id"}),
            headers=request.headers,
        )
    except ValueError as exc:
        raise DomainError(
            "INVALID_WEBHOOK_PAYLOAD",
            "Payload webhook tidak valid.",
            422,
        ) from exc
    payment = await payment_service.apply_webhook(
        db,
        payment_id=uuid.UUID(payload.payment_id),
        event=event,
    )
    return PaymentEnvelope(data=_payment_out(payment))
