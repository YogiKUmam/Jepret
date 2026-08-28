import base64
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.models import Booking, CreatorProfile, Review, User


def _encode_cursor(created_at: datetime, item_id: uuid.UUID) -> str:
    payload = f"{created_at.isoformat()}|{item_id}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        parts = raw.split("|", 1)
        if len(parts) != 2:
            raise ValueError("invalid cursor format")
        return datetime.fromisoformat(parts[0]), uuid.UUID(parts[1])
    except Exception as exc:
        raise DomainError("INVALID_CURSOR", "Cursor paginasi tidak valid.", 422) from exc


async def create_booking_review(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    client_user: User,
    rating: int,
    comment: str | None = None,
) -> Review:
    if rating < 1 or rating > 5:
        raise DomainError("INVALID_RATING", "Rating harus bernilai antara 1 sampai 5.", 422)

    booking_stmt = select(Booking).where(Booking.id == booking_id).with_for_update()
    booking = (await db.scalars(booking_stmt)).first()
    if not booking:
        raise DomainError("NOT_FOUND", "Booking tidak ditemukan.", 404)

    if booking.client_id != client_user.id:
        raise DomainError(
            "FORBIDDEN", "Hanya klien pembuat booking yang dapat memberikan ulasan.", 403
        )

    if booking.status != "completed":
        raise DomainError(
            "INVALID_STATUS", "Ulasan hanya dapat diberikan setelah sesi selesai (completed).", 409
        )

    existing = (await db.scalars(select(Review).where(Review.booking_id == booking_id))).first()
    if existing:
        raise DomainError(
            "REVIEW_ALREADY_SUBMITTED", "Ulasan untuk booking ini sudah pernah dikirim.", 409
        )

    clean_comment = comment.strip() if comment and comment.strip() else None

    review = Review(
        id=uuid.uuid4(),
        booking_id=booking.id,
        client_user_id=client_user.id,
        creator_profile_id=booking.creator_profile_id,
        rating=rating,
        comment=clean_comment,
    )
    db.add(review)
    await db.flush()

    calc_stmt = select(
        func.count(Review.id).label("count"),
        func.coalesce(func.avg(Review.rating), 0.0).label("average"),
    ).where(Review.creator_profile_id == booking.creator_profile_id)
    calc_res = (await db.execute(calc_stmt)).one()

    profile_stmt = (
        select(CreatorProfile)
        .where(CreatorProfile.id == booking.creator_profile_id)
        .with_for_update()
    )
    profile = (await db.scalars(profile_stmt)).one()
    profile.review_count = int(calc_res.count)
    profile.rating_average = round(float(calc_res.average), 2)

    await db.commit()

    reloaded_stmt = (
        select(Review).options(selectinload(Review.client)).where(Review.id == review.id)
    )
    return (await db.scalars(reloaded_stmt)).one()


async def get_booking_review(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    user: User,
) -> Review | None:
    booking = (await db.scalars(select(Booking).where(Booking.id == booking_id))).first()
    if not booking:
        raise DomainError("NOT_FOUND", "Booking tidak ditemukan.", 404)

    # Participant or Admin
    if not user.is_admin and booking.client_id != user.id:
        creator_profile = (
            await db.scalars(
                select(CreatorProfile).where(
                    CreatorProfile.id == booking.creator_profile_id,
                    CreatorProfile.user_id == user.id,
                )
            )
        ).first()
        if not creator_profile:
            raise DomainError("FORBIDDEN", "Anda tidak memiliki akses ke booking ini.", 403)

    stmt = (
        select(Review).options(selectinload(Review.client)).where(Review.booking_id == booking_id)
    )
    return (await db.scalars(stmt)).first()


async def list_creator_reviews(
    db: AsyncSession,
    *,
    creator_profile_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 10,
) -> tuple[list[Review], str | None, float, int]:
    profile = (
        await db.scalars(
            select(CreatorProfile).where(
                CreatorProfile.id == creator_profile_id,
                CreatorProfile.status == "approved",
            )
        )
    ).first()
    if not profile:
        raise DomainError("NOT_FOUND", "Profil kreator tidak ditemukan.", 404)

    query = (
        select(Review)
        .options(selectinload(Review.client))
        .where(Review.creator_profile_id == creator_profile_id)
    )

    if cursor:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        query = query.where(
            (Review.created_at < cursor_created_at)
            | ((Review.created_at == cursor_created_at) & (Review.id < cursor_id))
        )

    query = query.order_by(Review.created_at.desc(), Review.id.desc()).limit(limit + 1)
    results = (await db.scalars(query)).all()

    items = list(results[:limit])
    next_cursor: str | None = None
    if len(results) > limit:
        last_item = items[-1]
        next_cursor = _encode_cursor(last_item.created_at, last_item.id)

    return items, next_cursor, profile.rating_average, profile.review_count
