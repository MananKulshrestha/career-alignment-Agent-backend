from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.api import ProfileItemCreateRequest, ProfileItemResponse, UserProfileResponse
from app.services.profile_service import add_profile_item, get_profile

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
