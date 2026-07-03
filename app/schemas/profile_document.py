from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import ExtractionRisk, StrEnum
from app.schemas.profile import (
    ProfileItemCreate,
    ProfileItemKind,
    ProfileItemPayload,
    ProfileItemRead,
)

SUPPORTED_PROFILE_DOCUMENT_SCHEMA_VERSION = "1.0"


class SourceDocumentKind(StrEnum):
    RESUME = "resume"
    CERTIFICATION = "certification"
    PROJECT_DECK = "project_deck"
    TRANSCRIPT = "transcript"
    OTHER = "other"


class SourceDocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    TEXT_EXTRACTED = "text_extracted"
    EXTRACTION_DRAFTED = "extraction_drafted"
    APPROVED = "approved"
    FAILED = "failed"


class ProfileExtractionRunStatus(StrEnum):
    DRAFTED = "drafted"
    APPROVED = "approved"
    FAILED = "failed"


class ExtractionSupportLevel(StrEnum):
    DIRECT = "direct"
    LISTED_ONLY = "listed_only"
    INFERRED = "inferred"
    ADJACENT = "adjacent"
    CONFLICTING = "conflicting"
    INSUFFICIENT = "insufficient"


class ReviewRecommendation(StrEnum):
    APPROVE_AFTER_REVIEW = "approve_after_review"
    NEEDS_EDIT = "needs_edit"
    ASK_USER = "ask_user"
    DO_NOT_SAVE = "do_not_save"


class WarningSeverity(StrEnum):
    INFO = "info"
    MEDIUM = "medium"
    HIGH = "high"


class ApprovalAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ExtractionProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locator: str = Field(min_length=1)
    section_label: str | None = None
    source_snippet: str = Field(min_length=1, max_length=800)
    character_start: int | None = Field(default=None, ge=0)
    character_end: int | None = Field(default=None, ge=0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractionWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: WarningSeverity = WarningSeverity.INFO
    field_name: str | None = None


class ExcludedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    provenance: list[ExtractionProvenance] = Field(default_factory=list)
    severity: WarningSeverity = WarningSeverity.MEDIUM


class UnresolvedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(min_length=1)
    question: str = Field(min_length=1)
    priority: Literal["low", "medium", "high"] = "medium"


class ExtractedProfileDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str = Field(min_length=1)
    kind: ProfileItemKind
    source_item_id: str = Field(min_length=1)
    payload: ProfileItemPayload
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    support_level: ExtractionSupportLevel = ExtractionSupportLevel.INSUFFICIENT
    review_recommendation: ReviewRecommendation = ReviewRecommendation.NEEDS_EDIT
    provenance: list[ExtractionProvenance] = Field(default_factory=list)
    warnings: list[ExtractionWarning] = Field(default_factory=list)

    @field_validator("provenance")
    @classmethod
    def direct_items_need_provenance(
        cls, value: list[ExtractionProvenance], info
    ) -> list[ExtractionProvenance]:
        support_level = info.data.get("support_level")
        if (
            support_level
            in {
                ExtractionSupportLevel.DIRECT,
                ExtractionSupportLevel.ADJACENT,
                ExtractionSupportLevel.INFERRED,
                ExtractionSupportLevel.LISTED_ONLY,
            }
            and not value
        ):
            raise ValueError("source-backed profile drafts require provenance")
        return value


class ProfileDocumentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SUPPORTED_PROFILE_DOCUMENT_SCHEMA_VERSION
    detected_document_kind: SourceDocumentKind = SourceDocumentKind.OTHER
    document_summary: str = Field(default="", max_length=800)
    overall_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    extraction_risk: ExtractionRisk = ExtractionRisk.MEDIUM
    draft_items: list[ExtractedProfileDraft] = Field(default_factory=list)
    excluded_claims: list[ExcludedClaim] = Field(default_factory=list)
    document_warnings: list[ExtractionWarning] = Field(default_factory=list)
    unresolved_questions: list[UnresolvedQuestion] = Field(default_factory=list)


class SourceDocumentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    user_id: UUID
    kind: SourceDocumentKind
    filename: str
    content_type: str | None = None
    file_hash: str
    extracted_text_hash: str | None = None
    character_count: int = 0
    status: SourceDocumentStatus
    parser_warnings: list[dict] = Field(default_factory=list)
    error_message: str | None = None


class ProfileExtractionRunRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source_document_id: UUID
    user_id: UUID
    status: ProfileExtractionRunStatus
    model_name: str
    prompt_version: str
    schema_version: str
    success: bool
    error_message: str | None = None


class SourceDocumentExtractResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: SourceDocumentRead
    extraction_run: ProfileExtractionRunRead
    extraction: ProfileDocumentExtraction
    reused_existing_document: bool = False


class DraftApprovalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str = Field(min_length=1)
    action: ApprovalAction = ApprovalAction.APPROVE
    edited_kind: ProfileItemKind | None = None
    edited_payload: ProfileItemPayload | None = None
    edited_source_item_id: str | None = None
    manual_override: bool = False
    approval_notes: str | None = None


class SourceDocumentApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extraction_run_id: UUID
    items: list[DraftApprovalItem] = Field(min_length=1)


class SourceDocumentApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: SourceDocumentRead
    extraction_run: ProfileExtractionRunRead
    saved_items: list[ProfileItemRead] = Field(default_factory=list)
    approved_draft_ids: list[str] = Field(default_factory=list)
    rejected_draft_ids: list[str] = Field(default_factory=list)
    warnings: list[ExtractionWarning] = Field(default_factory=list)


class ProfileDraftApprovalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    kind: ProfileItemKind
    source_item_id: str
    payload: ProfileItemPayload
    support_level: ExtractionSupportLevel
    confidence: float
    provenance: list[ExtractionProvenance]
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    manual_override: bool = False
    approval_notes: str | None = None

    def to_profile_item_create(self) -> ProfileItemCreate:
        return ProfileItemCreate(
            kind=self.kind,
            source_item_id=self.source_item_id,
            payload=self.payload,
            is_active=True,
        )
