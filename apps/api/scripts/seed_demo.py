"""Seed idempotent demo accounts for local development only."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.db.models import CreatorProfile, User
from app.db.session import dispose_engine, get_engine

BASE_REVIEWED_AT = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)

DEMO_USERS = [
    {
        "email": "admin@jepret.local",
        "password": "admin12345",
        "full_name": "Admin Jepret",
        "is_admin": True,
    },
    {
        "email": "klien@jepret.local",
        "password": "klien12345",
        "full_name": "Klien Demo",
        "is_admin": False,
    },
]

# reviewed_at berjenjang: indeks lebih besar = di-approve lebih baru = tampil lebih dulu.
DEMO_CREATORS: list[dict[str, Any]] = [
    {
        "email": "kreator@jepret.local",
        "password": "kreator12345",
        "full_name": "Kreator Demo",
        "profile": {
            "display_name": "Studio Cahaya",
            "city": "Bandung",
            "bio": "Fotografer dan videografer pernikahan di Bandung.",
            "specialty": "wedding",
            "starting_price_idr": 1_500_000,
        },
    },
    {
        "email": "kreator2@jepret.local",
        "password": "kreator12345",
        "full_name": "Rana Lestari",
        "profile": {
            "display_name": "Rana Potret",
            "city": "Jakarta",
            "bio": "Spesialis potret keluarga dan personal branding.",
            "specialty": "portrait",
            "starting_price_idr": 750_000,
        },
    },
    {
        "email": "kreator3@jepret.local",
        "password": "kreator12345",
        "full_name": "Bagus Wijaya",
        "profile": {
            "display_name": "Kilat Studio",
            "city": "Jakarta",
            "bio": "Foto produk untuk UMKM dan katalog e-commerce.",
            "specialty": "product",
            "starting_price_idr": 500_000,
        },
    },
    {
        "email": "kreator4@jepret.local",
        "password": "kreator12345",
        "full_name": "Sari Utami",
        "profile": {
            "display_name": "Cerita Senja",
            "city": "Yogyakarta",
            "bio": "Dokumentasi pernikahan adat dan prewedding.",
            "specialty": "wedding",
            "starting_price_idr": 2_000_000,
        },
    },
    {
        "email": "kreator5@jepret.local",
        "password": "kreator12345",
        "full_name": "Dimas Pratama",
        "profile": {
            "display_name": "Gerak Frame",
            "city": "Surabaya",
            "bio": "Videografer acara perusahaan dan aftermovie.",
            "specialty": "video",
            "starting_price_idr": 3_000_000,
        },
    },
    {
        "email": "kreator6@jepret.local",
        "password": "kreator12345",
        "full_name": "Made Ayu",
        "profile": {
            "display_name": "Pulau Lensa",
            "city": "Denpasar",
            "bio": "Foto destinasi dan elopement di Bali.",
            "specialty": "wedding",
            "starting_price_idr": 4_500_000,
        },
    },
    {
        "email": "kreator7@jepret.local",
        "password": "kreator12345",
        "full_name": "Tono Saputra",
        "profile": {
            "display_name": "Panggung Kota",
            "city": "Bandung",
            "bio": "Dokumentasi konser, festival, dan acara komunitas.",
            "specialty": "event",
            "starting_price_idr": 1_000_000,
        },
    },
    {
        "email": "kreator8@jepret.local",
        "password": "kreator12345",
        "full_name": "Nina Kartika",
        "profile": {
            "display_name": "Piksel Rasa",
            "city": "Yogyakarta",
            "bio": "Foto kuliner untuk restoran dan kafe.",
            "specialty": "product",
            "starting_price_idr": 650_000,
        },
    },
]


async def _upsert_user(db: AsyncSession, entry: dict[str, Any]) -> User:
    user = await db.scalar(select(User).where(User.email == entry["email"]))
    if user is None:
        user = User(
            email=entry["email"],
            password_hash=hash_password(entry["password"]),
            full_name=entry["full_name"],
            is_admin=entry.get("is_admin", False),
        )
        db.add(user)
        await db.flush()
        print(f"created {entry['email']}")
    else:
        print(f"exists  {entry['email']}")
    return user


async def seed() -> None:
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as db:
        for entry in DEMO_USERS:
            await _upsert_user(db, entry)

        for index, entry in enumerate(DEMO_CREATORS):
            user = await _upsert_user(db, entry)
            profile = await db.scalar(
                select(CreatorProfile).where(CreatorProfile.user_id == user.id)
            )
            if profile is None:
                reviewed_at = BASE_REVIEWED_AT + timedelta(minutes=index)
                db.add(
                    CreatorProfile(
                        user_id=user.id,
                        status="approved",
                        submitted_at=reviewed_at,
                        reviewed_at=reviewed_at,
                        **entry["profile"],
                    )
                )
                print(f"created creator profile {entry['profile']['display_name']} (approved)")

        await db.commit()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed())
