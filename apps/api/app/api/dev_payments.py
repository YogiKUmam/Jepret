import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import DbSession, get_current_user
from app.api.payments import _payment_out
from app.api.schemas import PaymentEnvelope
from app.core.config import Environment, get_settings
from app.core.errors import DomainError
from app.db.models import User
from app.services import payments as payment_service

router = APIRouter(prefix="/api/v1/dev/payments", tags=["development payments"])


async def _dev_current_user(request: Request, db: DbSession) -> User:
    if get_settings().environment == Environment.PRODUCTION:
        raise DomainError(
            "DEV_ENDPOINT_DISABLED",
            "Endpoint pengembangan tidak tersedia.",
            404,
        )
    return await get_current_user(request, db)


DevCurrentUser = Annotated[User, Depends(_dev_current_user)]


@router.post("/{payment_id}/simulate-paid", response_model=PaymentEnvelope)
async def simulate_paid(
    payment_id: uuid.UUID,
    user: DevCurrentUser,
    db: DbSession,
) -> PaymentEnvelope:
    payment = await payment_service.simulate_paid(db, payment_id=payment_id, user=user)
    return PaymentEnvelope(data=_payment_out(payment))


@router.post("/{payment_id}/simulate-release", response_model=PaymentEnvelope)
async def simulate_release(
    payment_id: uuid.UUID,
    user: DevCurrentUser,
    db: DbSession,
) -> PaymentEnvelope:
    payment = await payment_service.simulate_release(db, payment_id=payment_id, user=user)
    return PaymentEnvelope(data=_payment_out(payment))
