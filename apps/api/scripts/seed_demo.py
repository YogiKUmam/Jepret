"""Seed idempotent demo accounts for local development only."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import hash_password
from app.db.models import CreatorProfile, User
from app.db.session import dispose_engine, get_engine

DEMO_USERS = [
    {"email": "admin@jepret.local", "password": "admin12345", "full_name": "Admin Jepret", "is_admin": True},
    {"email": "klien@jepret.local", "password": "klien12345", "full_name": "Klien Demo", "is_admin": False},
    {"email": "kreator@jepret.local", "password": "kreator12345", "full_name": "Kreator Demo", "is_admin": False},
]

DEMO_CREATOR_PROFILE = {
    "display_name": "Studio Cahaya",
    "city": "Bandung",
    "bio": "Fotografer dan videografer pernikahan di Bandung.",
    "specialty": "wedding",
    "starting_price_idr": 1_500_000,
}


async def seed() -> None:
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as db:
        for entry in DEMO_USERS:
            user = await db.scalar(select(User).where(User.email == entry["email"]))
            if user is None:
                user = User(
                    email=entry["email"],
                    password_hash=hash_password(entry["password"]),
                    full_name=entry["full_name"],
                    is_admin=entry["is_admin"],
                )
                db.add(user)
                await db.flush()
                print(f"created {entry['email']}")
            else:
                print(f"exists  {entry['email']}")

            if entry["email"] == "kreator@jepret.local":
                profile = await db.scalar(
                    select(CreatorProfile).where(CreatorProfile.user_id == user.id)
                )
                if profile is None:
                    now = datetime.now(UTC)
                    db.add(
                        CreatorProfile(
                            user_id=user.id,
                            status="approved",
                            submitted_at=now,
                            reviewed_at=now,
                            **DEMO_CREATOR_PROFILE,
                        )
                    )
                    print("created creator profile Studio Cahaya (approved)")

        await db.commit()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed())
