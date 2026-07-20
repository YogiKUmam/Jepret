from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.api.schemas import (
    CreatorDraftRequest,
    CreatorProfileEnvelope,
    CreatorProfileOut,
    UpdateProfileRequest,
    UserEnvelope,
    UserOut,
)
from app.services import profiles as profile_service

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.patch("/me", response_model=UserEnvelope)
async def update_me(payload: UpdateProfileRequest, user: CurrentUser, db: DbSession) -> UserEnvelope:
    updated = await profile_service.update_full_name(db, user=user, full_name=payload.full_name)
    profile = await profile_service.get_creator_profile(db, user=updated)
    return UserEnvelope(
        data=UserOut(
            id=updated.id,
            email=updated.email,
            full_name=updated.full_name,
            is_admin=updated.is_admin,
            creator_profile=(
                CreatorProfileOut.model_validate(profile, from_attributes=True) if profile else None
            ),
        )
    )


@router.put("/me/creator", response_model=CreatorProfileEnvelope)
async def upsert_creator(
    payload: CreatorDraftRequest, user: CurrentUser, db: DbSession
) -> CreatorProfileEnvelope:
    profile = await profile_service.upsert_creator_draft(
        db,
        user=user,
        display_name=payload.display_name,
        city=payload.city,
        bio=payload.bio,
        specialty=payload.specialty,
        starting_price_idr=payload.starting_price_idr,
    )
    return CreatorProfileEnvelope(
        data=CreatorProfileOut.model_validate(profile, from_attributes=True)
    )


@router.post("/me/creator/submit", response_model=CreatorProfileEnvelope)
async def submit_creator(user: CurrentUser, db: DbSession) -> CreatorProfileEnvelope:
    profile = await profile_service.submit_creator_profile(db, user=user)
    return CreatorProfileEnvelope(
        data=CreatorProfileOut.model_validate(profile, from_attributes=True)
    )
