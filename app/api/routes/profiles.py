from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.api import (
    ProfileItemCreateRequest,
    ProfileItemResponse,
    UserProfileContextResponse,
    UserProfileContextUpsertRequest,
    UserProfileResponse,
)
from app.services.profile_service import add_profile_item, get_profile, upsert_profile_context

router = APIRouter()


@router.post("/{user_id}/items", response_model=ProfileItemResponse)
def create_profile_item_route(
    user_id: UUID,
    request: ProfileItemCreateRequest,
    session: DbSession,
) -> ProfileItemResponse:
    return add_profile_item(session, user_id=user_id, request=request)


@router.get("/{user_id}", response_model=UserProfileResponse)
def get_profile_route(user_id: UUID, session: DbSession) -> UserProfileResponse:
    return get_profile(session, user_id=user_id)


@router.put("/{user_id}/context", response_model=UserProfileContextResponse)
def upsert_profile_context_route(
    user_id: UUID,
    request: UserProfileContextUpsertRequest,
    session: DbSession,
) -> UserProfileContextResponse:
    return upsert_profile_context(session, user_id=user_id, request=request)
