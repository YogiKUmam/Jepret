from dataclasses import FrozenInstanceError
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.integrations.payments import MockPaymentProvider, PaymentEvent, PaymentProvider


def provider() -> PaymentProvider:
    return MockPaymentProvider()


@pytest.mark.asyncio
async def test_create_payment_returns_deterministic_reference() -> None:
    payment_id = UUID("11111111-1111-1111-1111-111111111111")

    first_reference = await provider().create_payment(payment_id=payment_id, amount_idr=150_000)
    second_reference = await provider().create_payment(payment_id=payment_id, amount_idr=150_000)

    assert first_reference == second_reference == f"mock-{payment_id}"


@pytest.mark.asyncio
async def test_create_payment_rejects_non_positive_amount() -> None:
    with pytest.raises(ValueError):
        await provider().create_payment(payment_id=uuid4(), amount_idr=0)


@pytest.mark.asyncio
async def test_get_payment_status_returns_pending_for_mock_reference() -> None:
    payment_id = uuid4()

    status = await provider().get_payment_status(f"mock-{payment_id}")

    assert status == "pending"


@pytest.mark.asyncio
async def test_get_payment_status_rejects_non_mock_reference() -> None:
    with pytest.raises(ValueError):
        await provider().get_payment_status("external-reference")


@pytest.mark.asyncio
async def test_handle_webhook_normalizes_valid_event() -> None:
    event = await provider().handle_webhook(
        payload={"event_id": " provider-event-1 ", "event_type": "paid", "metadata": "ignored"},
        headers={"x-signature": "ignored"},
    )

    assert event == PaymentEvent(provider_event_id="provider-event-1", event_type="paid")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"event_id": None, "event_type": "paid"},
        {"event_id": 1, "event_type": "paid"},
        {"event_id": "", "event_type": "paid"},
        {"event_id": "   ", "event_type": "paid"},
        {"event_id": "event-1"},
        {"event_id": "event-1", "event_type": None},
        {"event_id": "event-1", "event_type": 1},
        {"event_id": "event-1", "event_type": "pending"},
    ],
)
async def test_handle_webhook_rejects_invalid_payload(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        await provider().handle_webhook(payload=payload, headers={})


@pytest.mark.asyncio
async def test_simulated_paid_event_is_deterministic() -> None:
    payment_id = UUID("22222222-2222-2222-2222-222222222222")
    mock_provider = MockPaymentProvider()

    first_event = await mock_provider.simulate_paid(payment_id)
    second_event = await mock_provider.simulate_paid(payment_id)

    assert (
        first_event
        == second_event
        == PaymentEvent(
            provider_event_id=f"mock-paid-{payment_id}",
            event_type="paid",
        )
    )


@pytest.mark.asyncio
async def test_refund_event_is_deterministic() -> None:
    payment_id = UUID("33333333-3333-3333-3333-333333333333")

    first_event = await provider().refund_payment(payment_id)
    second_event = await provider().refund_payment(payment_id)

    assert (
        first_event
        == second_event
        == PaymentEvent(
            provider_event_id=f"mock-refunded-{payment_id}",
            event_type="refunded",
        )
    )


@pytest.mark.asyncio
async def test_release_event_is_deterministic() -> None:
    payment_id = UUID("44444444-4444-4444-4444-444444444444")

    first_event = await provider().release_payment(payment_id)
    second_event = await provider().release_payment(payment_id)

    assert (
        first_event
        == second_event
        == PaymentEvent(
            provider_event_id=f"mock-released-{payment_id}",
            event_type="released",
        )
    )


def test_payment_event_is_frozen() -> None:
    event = PaymentEvent(provider_event_id="event-1", event_type="paid")

    with pytest.raises(FrozenInstanceError):
        cast(object, event).__setattr__("event_type", "failed")
