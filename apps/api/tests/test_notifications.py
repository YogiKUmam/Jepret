import uuid

import pytest

from app.services import notifications as notif_service


@pytest.mark.anyio
async def test_console_notification_provider() -> None:
    provider = notif_service.ConsoleNotificationProvider()

    email_sent = await provider.send_email(
        to_email="test@jepret.local",
        subject="Uji Notifikasi",
        body="Konten notifikasi uji.",
    )
    assert email_sent is True

    in_app_sent = await provider.send_in_app(
        user_id=uuid.uuid4(),
        title="Uji In-App",
        body="Konten in-app.",
        link_url="/booking/123",
    )
    assert in_app_sent is True


@pytest.mark.anyio
async def test_notification_helper_functions() -> None:
    booking_id = uuid.uuid4()

    res1 = await notif_service.notify_booking_status_changed(
        to_email="klien@jepret.local",
        booking_id=booking_id,
        new_status="confirmed",
    )
    assert res1 is True

    res2 = await notif_service.notify_dispute_opened(
        admin_email="admin@jepret.local",
        booking_id=booking_id,
        reason="Kreator tidak hadir",
    )
    assert res2 is True

    res3 = await notif_service.notify_dispute_resolved(
        to_email="klien@jepret.local",
        booking_id=booking_id,
        resolution="resolved_client",
    )
    assert res3 is True
