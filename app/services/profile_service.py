from __future__ import annotations

from uuid import UUID

from sqlmodel import Session, select

from app.models.tables import UserProfileItem, utc_now
from app.schemas.profile import ProfileItemCreate, ProfileItemRead, UserPreference, UserProfileRead


def add_profile_item(
    session: Session, *, user_id: UUID, request: ProfileItemCreate
) -> ProfileItemRead:
    existing = session.exec(
        select(UserProfileItem).where(
            UserProfileItem.user_id == user_id,
            UserProfileItem.source_item_id == request.source_item_id,
        )
    ).first()
    if existing:
        existing.kind = request.kind.value
        existing.payload = request.payload.model_dump(mode="json")
        existing.is_active = request.is_active
        existing.updated_at = utc_now()
        record = existing
    else:
        record = UserProfileItem(
            user_id=user_id,
            source_item_id=request.source_item_id,
            kind=request.kind.value,
            payload=request.payload.model_dump(mode="json"),
            is_active=request.is_active,
        )
        session.add(record)
    session.commit()
    session.refresh(record)
    return _profile_item_read(record)


def get_profile(
    session: Session,
    *,
    user_id: UUID,
    preferences: UserPreference | None = None,
) -> UserProfileRead:
    records = session.exec(
        select(UserProfileItem).where(
            UserProfileItem.user_id == user_id,
            UserProfileItem.is_active == True,  # noqa: E712
        )
    ).all()
    return UserProfileRead(
        user_id=str(user_id),
        preferences=preferences or UserPreference(),
        items=[_profile_item_read(record) for record in records],
    )


def _profile_item_read(record: UserProfileItem) -> ProfileItemRead:
    return ProfileItemRead(
        id=str(record.id),
        user_id=str(record.user_id),
        kind=record.kind,
        source_item_id=record.source_item_id,
        payload=record.payload,
        is_active=record.is_active,
    )
