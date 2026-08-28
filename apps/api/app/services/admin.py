from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dispute_schemas import AdminOverviewOut
from app.db.models import Booking, CreatorProfile, Dispute, Payment, User


async def get_admin_overview(db: AsyncSession) -> AdminOverviewOut:
    total_users = (
        await db.scalar(select(func.count(User.id)).where(User.is_admin.is_(False)))
    ) or 0

    total_creators = (await db.scalar(select(func.count(CreatorProfile.id)))) or 0

    pending_creator_applications = (
        await db.scalar(
            select(func.count(CreatorProfile.id)).where(CreatorProfile.status == "pending")
        )
    ) or 0

    total_bookings = (await db.scalar(select(func.count(Booking.id)))) or 0

    active_disputes = (
        await db.scalar(
            select(func.count(Dispute.id)).where(Dispute.status.in_(("open", "under_review")))
        )
    ) or 0

    total_gmv = (
        await db.scalar(
            select(func.coalesce(func.sum(Payment.amount_idr), 0)).where(
                Payment.status.in_(("held", "released", "paid"))
            )
        )
    ) or 0

    return AdminOverviewOut(
        total_users=int(total_users),
        total_creators=int(total_creators),
        pending_creator_applications=int(pending_creator_applications),
        total_bookings=int(total_bookings),
        active_disputes=int(active_disputes),
        total_gmv_idr=int(total_gmv),
    )
