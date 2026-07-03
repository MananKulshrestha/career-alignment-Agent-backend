from __future__ import annotations

import re
from uuid import UUID

from sqlmodel import Session, select

from app.core.config import settings
from app.core.errors import BlockedWorkflowError
from app.models.tables import ProfileExtractionRun, UserProfileItem, UserSourceDocument, utc_now
from app.schemas.profile import ProfileItemPayload, ProfileItemRead
from app.schemas.profile_document import (
    ApprovalAction,
    DraftApprovalItem,
    ExtractionSupportLevel,
    ProfileDocumentExtraction,
    ProfileDraftApprovalCandidate,
    ProfileExtractionRunRead,
    ProfileExtractionRunStatus,
    SourceDocumentApprovalRequest,
    SourceDocumentApprovalResponse,
    SourceDocumentExtractResponse,
    SourceDocumentKind,
    SourceDocumentRead,
    SourceDocumentStatus,
)
from app.services.agents import agent_gateway
from app.services.document_ingestion import ingest_source_document_bytes
from app.services.model_run_logger import record_model_run
from app.services.profile_service import add_kind_specific_evidence_gaps


async def extract_profile_document_from_bytes(
    session: Session,
    *,
    user_id: UUID,
    kind: SourceDocumentKind,
    filename: str,
    content_type: str | None,
    content: bytes,
) -> SourceDocumentExtractResponse:
    document, extracted_text, reused_existing = ingest_source_document_bytes(
        session,
        user_id=user_id,
        kind=kind,
        filename=filename,
        content_type=content_type,
        content=content,
    )

    extraction = await agent_gateway.extract_profile_items_from_document(
        document_kind=kind,
        text=extracted_text.text,
    )
    extraction = _normalize_extraction(extraction, document=document)
    run = ProfileExtractionRun(
        source_document_id=document.id,
        user_id=user_id,
        status=ProfileExtractionRunStatus.DRAFTED.value,
        model_name=settings.reliable_model if settings.llm_ready else "deterministic-fallback",
        prompt_version=agent_gateway.prompt_version,
        schema_version=extraction.schema_version,
        structured_json=extraction.model_dump(mode="json"),
        draft_items=[draft.model_dump(mode="json") for draft in extraction.draft_items],
        excluded_claims=[claim.model_dump(mode="json") for claim in extraction.excluded_claims],
        warnings=[warning.model_dump(mode="json") for warning in extraction.document_warnings],
        unresolved_questions=[
            question.model_dump(mode="json") for question in extraction.unresolved_questions
        ],
        success=True,
    )
    document.status = SourceDocumentStatus.EXTRACTION_DRAFTED.value
    document.updated_at = utc_now()
    session.add(run)
    record_model_run(
        session,
        stage="profile_document_extraction",
        model_name=run.model_name,
        user_id=user_id,
        input_summary={
            "source_document_id": str(document.id),
            "document_kind": kind.value,
            "chars": extracted_text.character_count,
        },
        output_summary={
            "draft_item_count": len(extraction.draft_items),
            "risk": extraction.extraction_risk.value,
        },
    )
    session.commit()
    session.refresh(document)
    session.refresh(run)
    return SourceDocumentExtractResponse(
        document=_source_document_read(document),
        extraction_run=_extraction_run_read(run),
        extraction=extraction,
        reused_existing_document=reused_existing,
    )


def approve_profile_document_drafts(
    session: Session,
    *,
    user_id: UUID,
    document_id: UUID,
    request: SourceDocumentApprovalRequest,
) -> SourceDocumentApprovalResponse:
    document = _get_user_document(session, user_id=user_id, document_id=document_id)
    run = session.get(ProfileExtractionRun, request.extraction_run_id)
    if not run or run.user_id != user_id or run.source_document_id != document.id:
        raise BlockedWorkflowError("profile extraction run not found for this user document")
    if not run.success or run.status == ProfileExtractionRunStatus.FAILED.value:
        raise BlockedWorkflowError("failed profile extraction runs cannot be approved")

    extraction = ProfileDocumentExtraction.model_validate(run.structured_json)
    drafts_by_id = {draft.draft_id: draft for draft in extraction.draft_items}
    approval_results = list(run.approval_results)
    approved_draft_ids = set(run.approved_draft_ids)
    rejected_draft_ids = set(run.rejected_draft_ids)
    saved_items: list[ProfileItemRead] = []

    for item in request.items:
        draft = drafts_by_id.get(item.draft_id)
        if not draft:
            raise BlockedWorkflowError(f"unknown profile extraction draft: {item.draft_id}")
        if item.action == ApprovalAction.REJECT:
            rejected_draft_ids.add(item.draft_id)
            continue

        existing_approved = _approved_result_for_draft(approval_results, item.draft_id)
        if existing_approved:
            existing = session.get(UserProfileItem, UUID(existing_approved["profile_item_id"]))
            if existing:
                saved_items.append(_profile_item_read(existing))
                approved_draft_ids.add(item.draft_id)
                continue

        candidate = _approval_candidate_from_draft(
            item=item,
            draft=draft,
            document=document,
            run=run,
        )
        existing = session.exec(
            select(UserProfileItem).where(
                UserProfileItem.user_id == user_id,
                UserProfileItem.source_item_id == candidate.source_item_id,
            )
        ).first()
        if existing:
            if _record_matches_approval(existing, run_id=run.id, draft_id=candidate.draft_id):
                saved_items.append(_profile_item_read(existing))
                approved_draft_ids.add(candidate.draft_id)
                continue
            raise BlockedWorkflowError(
                "approved draft would overwrite an existing profile item; "
                f"choose a different source_item_id: {candidate.source_item_id}"
            )

        payload = add_kind_specific_evidence_gaps(candidate.kind, candidate.payload)
        record = UserProfileItem(
            user_id=user_id,
            source_item_id=candidate.source_item_id,
            kind=candidate.kind.value,
            payload=payload.model_dump(mode="json"),
            is_active=True,
        )
        session.add(record)
        session.flush()
        saved_items.append(_profile_item_read(record))
        approved_draft_ids.add(candidate.draft_id)
        approval_results.append(
            {
                "draft_id": candidate.draft_id,
                "profile_item_id": str(record.id),
                "source_item_id": candidate.source_item_id,
                "manual_override": candidate.manual_override,
            }
        )

    run.approved_draft_ids = sorted(approved_draft_ids)
    run.rejected_draft_ids = sorted(rejected_draft_ids)
    run.approval_results = approval_results
    if approved_draft_ids:
        run.status = ProfileExtractionRunStatus.APPROVED.value
        document.status = SourceDocumentStatus.APPROVED.value
    run.updated_at = utc_now()
    document.updated_at = utc_now()
    session.commit()
    session.refresh(document)
    session.refresh(run)
    return SourceDocumentApprovalResponse(
        document=_source_document_read(document),
        extraction_run=_extraction_run_read(run),
        saved_items=saved_items,
        approved_draft_ids=run.approved_draft_ids,
        rejected_draft_ids=run.rejected_draft_ids,
    )


def _approval_candidate_from_draft(
    *,
    item: DraftApprovalItem,
    draft,
    document: UserSourceDocument,
    run: ProfileExtractionRun,
) -> ProfileDraftApprovalCandidate:
    support_level = draft.support_level
    if support_level == ExtractionSupportLevel.INSUFFICIENT and not item.manual_override:
        raise BlockedWorkflowError(
            f"draft {draft.draft_id} has insufficient evidence and requires user edits"
        )
    if support_level == ExtractionSupportLevel.CONFLICTING and not item.manual_override:
        raise BlockedWorkflowError(
            f"draft {draft.draft_id} has conflicting evidence and must be resolved before saving"
        )
    if not draft.provenance and not item.manual_override:
        raise BlockedWorkflowError(f"draft {draft.draft_id} is missing provenance")

    kind = item.edited_kind or draft.kind
    payload = item.edited_payload or draft.payload
    source_item_id = _safe_source_item_id(item.edited_source_item_id or draft.source_item_id)
    if not _payload_has_meaningful_content(payload):
        raise BlockedWorkflowError(f"draft {draft.draft_id} has no meaningful profile content")

    metadata = {
        "source_document_id": str(document.id),
        "extraction_run_id": str(run.id),
        "draft_id": draft.draft_id,
        "support_level": support_level.value,
        "extraction_confidence": draft.confidence,
        "approved_from_document": True,
        "manual_override": item.manual_override,
        "provenance": [provenance.model_dump(mode="json") for provenance in draft.provenance],
        "extraction_warnings": [warning.model_dump(mode="json") for warning in draft.warnings],
    }
    if item.approval_notes:
        metadata["approval_notes"] = item.approval_notes
    if support_level == ExtractionSupportLevel.LISTED_ONLY and not payload.evidence_source:
        metadata_evidence = "Listed in uploaded source document; practical ownership not confirmed."
        payload = payload.model_copy(update={"evidence_source": metadata_evidence}, deep=True)
    payload = payload.model_copy(update=metadata, deep=True)

    return ProfileDraftApprovalCandidate(
        draft_id=draft.draft_id,
        kind=kind,
        source_item_id=source_item_id,
        payload=payload,
        support_level=support_level,
        confidence=draft.confidence,
        provenance=draft.provenance,
        warnings=draft.warnings,
        manual_override=item.manual_override,
        approval_notes=item.approval_notes,
    )


def _normalize_extraction(
    extraction: ProfileDocumentExtraction,
    *,
    document: UserSourceDocument,
) -> ProfileDocumentExtraction:
    seen: set[str] = set()
    normalized_drafts = []
    for draft in extraction.draft_items:
        source_item_id = _safe_source_item_id(draft.source_item_id)
        if source_item_id in seen:
            source_item_id = f"{source_item_id}_{len(seen) + 1}"
        seen.add(source_item_id)
        normalized_drafts.append(draft.model_copy(update={"source_item_id": source_item_id}))
    if extraction.detected_document_kind.value != document.kind:
        warning = {
            "code": "document_kind_mismatch",
            "message": (
                "Detected document kind differs from the kind selected during upload; "
                "review extracted drafts carefully."
            ),
            "severity": "medium",
        }
        document.parser_warnings = [*document.parser_warnings, warning]
    return extraction.model_copy(update={"draft_items": normalized_drafts}, deep=True)


def _get_user_document(
    session: Session,
    *,
    user_id: UUID,
    document_id: UUID,
) -> UserSourceDocument:
    document = session.get(UserSourceDocument, document_id)
    if not document or document.user_id != user_id:
        raise BlockedWorkflowError("source document not found for this user")
    return document


def _source_document_read(document: UserSourceDocument) -> SourceDocumentRead:
    return SourceDocumentRead(
        id=document.id,
        user_id=document.user_id,
        kind=document.kind,
        filename=document.filename,
        content_type=document.content_type,
        file_hash=document.file_hash,
        extracted_text_hash=document.extracted_text_hash,
        character_count=document.character_count,
        status=document.status,
        parser_warnings=document.parser_warnings,
        error_message=document.error_message,
    )


def _extraction_run_read(run: ProfileExtractionRun) -> ProfileExtractionRunRead:
    return ProfileExtractionRunRead(
        id=run.id,
        source_document_id=run.source_document_id,
        user_id=run.user_id,
        status=run.status,
        model_name=run.model_name,
        prompt_version=run.prompt_version,
        schema_version=run.schema_version,
        success=run.success,
        error_message=run.error_message,
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


def _approved_result_for_draft(
    approval_results: list[dict],
    draft_id: str,
) -> dict | None:
    for result in approval_results:
        if result.get("draft_id") == draft_id and result.get("profile_item_id"):
            return result
    return None


def _record_matches_approval(record: UserProfileItem, *, run_id: UUID, draft_id: str) -> bool:
    return (
        record.payload.get("extraction_run_id") == str(run_id)
        and record.payload.get("draft_id") == draft_id
    )


def _safe_source_item_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip()).strip("_").lower()
    if not safe:
        raise BlockedWorkflowError("approved draft source_item_id cannot be empty")
    return safe[:160]


def _payload_has_meaningful_content(payload: ProfileItemPayload) -> bool:
    return any(
        [
            payload.description.strip(),
            payload.title,
            payload.organization,
            payload.skills,
            payload.achievements,
            payload.metrics,
            payload.tech_stack,
            payload.responsibilities,
            payload.coursework,
            payload.issuer,
        ]
    )
