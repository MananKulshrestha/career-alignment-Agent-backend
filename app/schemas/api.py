from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import (
    ApplicationStatus,
    MatchVerdict,
    SavedStatus,
    StrEnum,
    TailoringStatus,
)
from app.schemas.job_spec import JobSpec
from app.schemas.profile import (
    ProfileItemCreate,
    ProfileItemRead,
    UserPreference,
    UserProfileContextRead,
    UserProfileContextUpsert,
    UserProfileRead,
)
from app.schemas.resume import CompileResult, ResumeContent, TemplatePlan
from app.schemas.selection import SelectionApproval, SelectionPlan


class SubmissionKind(StrEnum):
    URL = "url"
    QUERY = "query"
    TEXT = "text"


class JobIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    kind: SubmissionKind
    url: str | None = None
    query: str | None = None
    pasted_text: str | None = None
    match_threshold: float = Field(default=0.65, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def exactly_one_submission_value(self) -> "JobIngestRequest":
        expected = {
            SubmissionKind.URL: self.url,
            SubmissionKind.QUERY: self.query,
            SubmissionKind.TEXT: self.pasted_text,
        }[self.kind]
        if not expected or not expected.strip():
            raise ValueError(f"{self.kind.value} submissions require a matching non-empty value")
        return self


class JobRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    company: str
    canonical_url: str | None
    source_hash: str
    status: str


class JobIngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: JobRead
    job_spec: JobSpec
    reused_existing_job: bool = False
    match: "UserJobMatchRead | None" = None


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    preferences: UserPreference = Field(default_factory=UserPreference)


class UserJobMatchRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    user_id: UUID
    job_id: UUID
    match_score: float
    match_verdict: MatchVerdict
    preference_failures: list[str]
    missing_requirements: list[dict]
    adjacent_evidence: list[dict]
    short_explanation: str
    saved_status: SavedStatus
    application_status: ApplicationStatus
    tailoring_status: TailoringStatus


class JobListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: JobRead
    match: UserJobMatchRead | None = None


ProfileItemCreateRequest = ProfileItemCreate
ProfileItemResponse = ProfileItemRead
UserProfileContextUpsertRequest = UserProfileContextUpsert
UserProfileContextResponse = UserProfileContextRead
UserProfileResponse = UserProfileRead


class TailoringSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    job_id: UUID
    revision_notes: str | None = None


class TailoringSessionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    user_id: UUID
    job_id: UUID
    status: TailoringStatus
    selection_plan: SelectionPlan | None = None
    template_plan: TemplatePlan | None = None
    resume_content: ResumeContent | None = None


SelectionApprovalRequest = SelectionApproval


class ResumeGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_request: str | None = None


class ResumeGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: TailoringSessionRead
    resume_content: ResumeContent


class ResumeCompileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: TailoringSessionRead
    compile_result: CompileResult


JobIngestResponse.model_rebuild()
