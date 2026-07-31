from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

PaymentEventType = Literal["paid", "failed", "refunded", "released"]


@dataclass(frozen=True)
class PaymentEvent:
    provider_event_id: str
    event_type: PaymentEventType


class PaymentProvider(Protocol):
    name: str

    async def create_payment(self, *, payment_id: UUID, amount_idr: int) -> str: ...

    async def get_payment_status(self, provider_reference: str) -> str: ...

    async def handle_webhook(
        self,
        *,
        payload: Mapping[str, object],
        headers: Mapping[str, str],
    ) -> PaymentEvent: ...

    async def refund_payment(self, payment_id: UUID) -> PaymentEvent: ...

    async def release_payment(self, payment_id: UUID) -> PaymentEvent: ...


class MockPaymentProvider:
    name = "mock"

    async def create_payment(self, *, payment_id: UUID, amount_idr: int) -> str:
        if type(amount_idr) is not int or amount_idr <= 0:
            raise ValueError("Payment amount must be a positive integer")
        return f"mock-{payment_id}"

    async def get_payment_status(self, provider_reference: str) -> str:
        if not provider_reference.startswith("mock-"):
            raise ValueError("Invalid mock payment reference")
        try:
            payment_id = UUID(provider_reference.removeprefix("mock-"))
        except ValueError as error:
            raise ValueError("Invalid mock payment reference") from error
        if provider_reference != f"mock-{payment_id}":
            raise ValueError("Invalid mock payment reference")
        return "pending"

    async def handle_webhook(
        self,
        *,
        payload: Mapping[str, object],
        headers: Mapping[str, str],
    ) -> PaymentEvent:
        del headers
        event_id = payload.get("event_id")
        event_type = payload.get("event_type")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("Webhook event_id must be a non-empty string")
        if not isinstance(event_type, str):
            raise ValueError("Webhook event_type must be paid or failed")
        if event_type == "paid":
            normalized_event_type: PaymentEventType = "paid"
        elif event_type == "failed":
            normalized_event_type = "failed"
        else:
            raise ValueError("Webhook event_type must be paid or failed")
        return PaymentEvent(provider_event_id=event_id.strip(), event_type=normalized_event_type)

    async def simulate_paid(self, payment_id: UUID) -> PaymentEvent:
        return PaymentEvent(provider_event_id=f"mock-paid-{payment_id}", event_type="paid")

    async def refund_payment(self, payment_id: UUID) -> PaymentEvent:
        return PaymentEvent(provider_event_id=f"mock-refunded-{payment_id}", event_type="refunded")

    async def release_payment(self, payment_id: UUID) -> PaymentEvent:
        return PaymentEvent(provider_event_id=f"mock-released-{payment_id}", event_type="released")
