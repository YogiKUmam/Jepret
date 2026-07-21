import base64
import binascii
import uuid
from datetime import datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.models import CreatorProfile

MAX_LIMIT = 50
DEFAULT_LIMIT = 12


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def encode_cursor(reviewed_at: datetime, creator_id: uuid.UUID) -> str:
    raw = f"{reviewed_at.isoformat()}|{creator_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        reviewed_raw, separator, id_raw = raw.partition("|")
        if not separator:
            raise ValueError("cursor is missing its separator")
        return datetime.fromisoformat(reviewed_raw), uuid.UUID(id_raw)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise DomainError("INVALID_CURSOR", "Cursor tidak valid.", status_code=422) from exc


async def list_creators(
    db: AsyncSession,
    *,
    q: str | None = None,
    city: str | None = None,
    specialty: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> tuple[list[CreatorProfile], str | None]:
    stmt = select(CreatorProfile).where(CreatorProfile.status == "approved")
    if q:
        pattern = f"%{_escape_like(q)}%"
        stmt = stmt.where(
            CreatorProfile.display_name.ilike(pattern, escape="\\")
            | CreatorProfile.bio.ilike(pattern, escape="\\")
        )
    if city:
        stmt = stmt.where(func.lower(CreatorProfile.city) == city.lower())
    if specialty:
        stmt = stmt.where(func.lower(CreatorProfile.specialty) == specialty.lower())
    if min_price is not None:
        stmt = stmt.where(CreatorProfile.starting_price_idr >= min_price)
    if max_price is not None:
        stmt = stmt.where(CreatorProfile.starting_price_idr <= max_price)
    if cursor:
        cursor_reviewed_at, cursor_id = decode_cursor(cursor)
        stmt = stmt.where(
            tuple_(CreatorProfile.reviewed_at, CreatorProfile.id) < (cursor_reviewed_at, cursor_id)
        )
    stmt = stmt.order_by(CreatorProfile.reviewed_at.desc(), CreatorProfile.id.desc()).limit(
        limit + 1
    )
    rows = list((await db.scalars(stmt)).all())
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        if last.reviewed_at is not None:
            next_cursor = encode_cursor(last.reviewed_at, last.id)
    return rows, next_cursor


async def get_creator(db: AsyncSession, *, creator_id: uuid.UUID) -> CreatorProfile:
    profile = await db.scalar(
        select(CreatorProfile).where(
            CreatorProfile.id == creator_id, CreatorProfile.status == "approved"
        )
    )
    if profile is None:
        raise DomainError("NOT_FOUND", "Kreator tidak ditemukan.", status_code=404)
    return profile
