import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models import CreatorProfile, User

EDITABLE_STATUSES = frozenset({"draft", "rejected"})


async def update_full_name(db: AsyncSession, *, user: User, full_name: str) -> User:
    user.full_name = full_name.strip()
    await db.commit()
    return user


async def get_creator_profile(db: AsyncSession, *, user: User) -> CreatorProfile | None:
    return await db.scalar(select(CreatorProfile).where(CreatorProfile.user_id == user.id))


async def upsert_creator_draft(
    db: AsyncSession,
    *,
    user: User,
    display_name: str,
    city: str,
    bio: str,
    specialty: str,
    starting_price_idr: int,
) -> CreatorProfile:
    profile = await get_creator_profile(db, user=user)
    if profile is None:
        profile = CreatorProfile(user_id=user.id, starting_price_idr=0, status="draft")
        db.add(profile)
    elif profile.status not in EDITABLE_STATUSES:
        raise DomainError(
            "INVALID_STATUS_TRANSITION",
            "Profil kreator tidak dapat diubah saat menunggu atau sudah terverifikasi.",
            409,
        )

    profile.display_name = display_name.strip()
    profile.city = city.strip()
    profile.bio = bio.strip()
    profile.specialty = specialty.strip()
    profile.starting_price_idr = starting_price_idr
    profile.status = "draft"
    profile.submitted_at = None
    profile.reviewed_at = None
    await db.commit()
    await db.refresh(profile)
    return profile


async def submit_creator_profile(db: AsyncSession, *, user: User) -> CreatorProfile:
    profile = await get_creator_profile(db, user=user)
    if profile is None:
        raise DomainError(
            "CREATOR_PROFILE_INCOMPLETE", "Lengkapi profil kreator terlebih dahulu.", 422
        )
    if profile.status != "draft":
        raise DomainError(
            "INVALID_STATUS_TRANSITION", "Pengajuan hanya dapat dilakukan dari status draft.", 409
        )
    if not (profile.display_name and profile.city and profile.specialty):
        raise DomainError(
            "CREATOR_PROFILE_INCOMPLETE", "Lengkapi profil kreator terlebih dahulu.", 422
        )

    profile.status = "pending"
    profile.submitted_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(profile)
    return profile


async def list_pending_applications(db: AsyncSession) -> list[tuple[CreatorProfile, User]]:
    rows = await db.execute(
        select(CreatorProfile, User)
        .join(User, User.id == CreatorProfile.user_id)
        .where(CreatorProfile.status == "pending")
        .order_by(CreatorProfile.submitted_at)
    )
    return [(profile, user) for profile, user in rows.all()]


async def _review_application(
    db: AsyncSession, *, profile_id: uuid.UUID, new_status: str
) -> CreatorProfile:
    profile = await db.scalar(
        select(CreatorProfile).where(CreatorProfile.id == profile_id).with_for_update()
    )
    if profile is None:
        raise DomainError("NOT_FOUND", "Pengajuan kreator tidak ditemukan.", 404)
    if profile.status != "pending":
        raise DomainError(
            "INVALID_STATUS_TRANSITION",
            "Hanya pengajuan berstatus pending yang dapat direview.",
            409,
        )

    profile.status = new_status
    profile.reviewed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(profile)
    return profile


async def approve_application(db: AsyncSession, *, profile_id: uuid.UUID) -> CreatorProfile:
    return await _review_application(db, profile_id=profile_id, new_status="approved")


async def reject_application(db: AsyncSession, *, profile_id: uuid.UUID) -> CreatorProfile:
    return await _review_application(db, profile_id=profile_id, new_status="rejected")
