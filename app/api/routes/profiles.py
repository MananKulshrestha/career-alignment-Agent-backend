from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import DbSession
from app.schemas.api import ProfileItemCreateRequest, ProfileItemResponse, UserProfileResponse
from app.schemas.profile_document import (
    SourceDocumentApprovalRequest,
    SourceDocumentApprovalResponse,
    SourceDocumentExtractResponse,
    SourceDocumentKind,
)
from app.services.profile_extraction import (
    approve_profile_document_drafts,
    extract_profile_document_from_bytes,
)
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


@router.post("/{user_id}/source-documents/extract", response_model=SourceDocumentExtractResponse)
async def extract_source_document_route(
    user_id: UUID,
    session: DbSession,
    file: UploadFile = File(...),
    kind: SourceDocumentKind = Form(default=SourceDocumentKind.OTHER),
) -> SourceDocumentExtractResponse:
    content = await file.read()
    return await extract_profile_document_from_bytes(
        session,
        user_id=user_id,
        kind=kind,
        filename=file.filename or "source-document",
        content_type=file.content_type,
        content=content,
    )


@router.post(
    "/{user_id}/source-documents/{document_id}/approve",
    response_model=SourceDocumentApprovalResponse,
)
def approve_source_document_route(
    user_id: UUID,
    document_id: UUID,
    request: SourceDocumentApprovalRequest,
    session: DbSession,
) -> SourceDocumentApprovalResponse:
    return approve_profile_document_drafts(
        session,
        user_id=user_id,
        document_id=document_id,
        request=request,
    )
