import logging
import uuid
from typing import Protocol

logger = logging.getLogger("jepret.notifications")


class NotificationProvider(Protocol):
    async def send_email(self, *, to_email: str, subject: str, body: str) -> bool: ...

    async def send_in_app(
        self,
        *,
        user_id: uuid.UUID,
        title: str,
        body: str,
        link_url: str | None = None,
    ) -> bool: ...


class ConsoleNotificationProvider:
    """Development and test notification provider outputting to structured logs."""

    async def send_email(self, *, to_email: str, subject: str, body: str) -> bool:
        logger.info(
            "notification.email",
            extra={
                "to_email": to_email,
                "subject": subject,
                "body": body,
            },
        )
        return True

    async def send_in_app(
        self,
        *,
        user_id: uuid.UUID,
        title: str,
        body: str,
        link_url: str | None = None,
    ) -> bool:
        logger.info(
            "notification.in_app",
            extra={
                "user_id": str(user_id),
                "title": title,
                "body": body,
                "link_url": link_url,
            },
        )
        return True


DEFAULT_PROVIDER: NotificationProvider = ConsoleNotificationProvider()


async def notify_booking_status_changed(
    *,
    to_email: str,
    booking_id: uuid.UUID,
    new_status: str,
    provider: NotificationProvider = DEFAULT_PROVIDER,
) -> bool:
    subject = f"[Jepret] Status Booking #{str(booking_id)[:8]} Berubah: {new_status}"
    body = (
        f"Status pesanan booking Anda dengan ID {booking_id} telah berubah menjadi: {new_status}.\n"
        "Silakan buka ruang kerja booking untuk detail lebih lanjut."
    )
    return await provider.send_email(to_email=to_email, subject=subject, body=body)


async def notify_dispute_opened(
    *,
    admin_email: str,
    booking_id: uuid.UUID,
    reason: str,
    provider: NotificationProvider = DEFAULT_PROVIDER,
) -> bool:
    subject = f"[Jepret Admin] Sengketa Baru Diajukan: Booking #{str(booking_id)[:8]}"
    body = (
        f"Klien telah mengajukan sengketa untuk Booking #{booking_id} dengan alasan: {reason}.\n"
        "Silakan login ke panel admin (/admin/sengketa) untuk melakukan mediasi."
    )
    return await provider.send_email(to_email=admin_email, subject=subject, body=body)


async def notify_dispute_resolved(
    *,
    to_email: str,
    booking_id: uuid.UUID,
    resolution: str,
    provider: NotificationProvider = DEFAULT_PROVIDER,
) -> bool:
    subject = f"[Jepret] Sengketa Booking #{str(booking_id)[:8]} Telah Diselesaikan"
    body = (
        f"Sengketa untuk Booking #{booking_id} telah diputuskan oleh admin "
        f"dengan hasil: {resolution}.\n"
        "Terima kasih atas kerja samanya."
    )
    return await provider.send_email(to_email=to_email, subject=subject, body=body)
