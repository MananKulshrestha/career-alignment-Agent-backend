from uuid import uuid4

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.core.errors import BlockedWorkflowError
from app.models.tables import UserProfileItem
from app.schemas.profile import ProfileItemCreate, ProfileItemKind, ProfileItemPayload
from app.schemas.profile_document import (
    DraftApprovalItem,
    ExtractionSupportLevel,
    SourceDocumentApprovalRequest,
    SourceDocumentKind,
)
from app.services.fallbacks import fallback_profile_document_extraction
from app.services.profile_extraction import (
    approve_profile_document_drafts,
    extract_profile_document_from_bytes,
)
from app.services.profile_service import add_profile_item


def _memory_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_keyless_profile_document_extraction_preserves_limiting_claims() -> None:
    extraction = fallback_profile_document_extraction(
        document_kind=SourceDocumentKind.PROJECT_DECK,
        text=(
            "Project: Deployment Deck\n"
            "Built Docker packaging for the app. "
            "A teammate managed Kubernetes deployment."
        ),
    )

    skill_draft = next(draft for draft in extraction.draft_items if draft.kind == "skill")

    assert skill_draft.support_level == ExtractionSupportLevel.LISTED_ONLY
    assert any(claim.claim == "Kubernetes ownership" for claim in extraction.excluded_claims)


@pytest.mark.asyncio
async def test_source_document_approval_creates_profile_item_with_provenance(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "source_documents_dir", tmp_path)
    user_id = uuid4()
    with _memory_session() as session:
        response = await extract_profile_document_from_bytes(
            session,
            user_id=user_id,
            kind=SourceDocumentKind.PROJECT_DECK,
            filename="project-deck.txt",
            content_type="text/plain",
            content=(
                b"Project: Backend Tracker\n"
                b"Built FastAPI and PostgreSQL APIs with Docker packaging."
            ),
        )
        approval = approve_profile_document_drafts(
            session,
            user_id=user_id,
            document_id=response.document.id,
            request=SourceDocumentApprovalRequest(
                extraction_run_id=response.extraction_run.id,
                items=[DraftApprovalItem(draft_id="draft_project_uploaded_project")],
            ),
        )

        assert len(approval.saved_items) == 1
        saved = approval.saved_items[0]
        assert saved.kind == ProfileItemKind.PROJECT
        assert saved.payload.source_document_id == str(response.document.id)
        assert saved.payload.extraction_run_id == str(response.extraction_run.id)
        assert saved.payload.provenance
        assert "measurable_impact" in {gap.field_name for gap in saved.payload.evidence_gaps}


@pytest.mark.asyncio
async def test_source_document_approval_is_idempotent_for_same_draft(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "source_documents_dir", tmp_path)
    user_id = uuid4()
    with _memory_session() as session:
        response = await extract_profile_document_from_bytes(
            session,
            user_id=user_id,
            kind=SourceDocumentKind.PROJECT_DECK,
            filename="project-deck.txt",
            content_type="text/plain",
            content=b"Project: Backend Tracker\nBuilt FastAPI services with PostgreSQL.",
        )
        request = SourceDocumentApprovalRequest(
            extraction_run_id=response.extraction_run.id,
            items=[DraftApprovalItem(draft_id="draft_project_uploaded_project")],
        )

        first = approve_profile_document_drafts(
            session,
            user_id=user_id,
            document_id=response.document.id,
            request=request,
        )
        second = approve_profile_document_drafts(
            session,
            user_id=user_id,
            document_id=response.document.id,
            request=request,
        )
        records = session.exec(select(UserProfileItem)).all()

        assert first.saved_items[0].id == second.saved_items[0].id
        assert len(records) == 1


@pytest.mark.asyncio
async def test_source_document_approval_does_not_overwrite_curated_profile_items(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "source_documents_dir", tmp_path)
    user_id = uuid4()
    with _memory_session() as session:
        add_profile_item(
            session,
            user_id=user_id,
            request=ProfileItemCreate(
                kind=ProfileItemKind.PROJECT,
                source_item_id="doc_project_uploaded_project",
                payload=ProfileItemPayload(
                    title="Curated Project",
                    description="A manually curated project should not be overwritten.",
                ),
            ),
        )
        response = await extract_profile_document_from_bytes(
            session,
            user_id=user_id,
            kind=SourceDocumentKind.PROJECT_DECK,
            filename="project-deck.txt",
            content_type="text/plain",
            content=b"Project: Backend Tracker\nBuilt FastAPI services with PostgreSQL.",
        )

        with pytest.raises(BlockedWorkflowError, match="overwrite an existing profile item"):
            approve_profile_document_drafts(
                session,
                user_id=user_id,
                document_id=response.document.id,
                request=SourceDocumentApprovalRequest(
                    extraction_run_id=response.extraction_run.id,
                    items=[DraftApprovalItem(draft_id="draft_project_uploaded_project")],
                ),
            )
