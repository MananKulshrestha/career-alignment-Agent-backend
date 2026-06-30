from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.enums import (
    ApplicationStatus,
    ExtractionRisk,
    JobStatus,
    MatchVerdict,
    SavedStatus,
    TailoringStatus,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin(SQLModel):
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Job(TimestampMixin, table=True):
    __tablename__ = "jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    canonical_url: str | None = Field(default=None, index=True)
    url_hash: str | None = Field(
        default=None,
        sa_column=Column(String(64), unique=True, nullable=True, index=True),
    )
    source_hash: str = Field(sa_column=Column(String(64), unique=True, nullable=False, index=True))
    title: str = Field(default="Unknown role", index=True)
    company: str = Field(default="Unknown company", index=True)
    location: str | None = None
    remote_policy: str = "unknown"
    salary_min: float | None = None
    salary_max: float | None = None
    deadline: str | None = None
    expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    status: str = Field(default=JobStatus.ACTIVE.value, index=True)


class JobSpecRecord(TimestampMixin, table=True):
    __tablename__ = "job_specs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    job_id: UUID = Field(foreign_key="jobs.id", index=True)
    version: int = Field(default=1, ge=1)
    schema_version: str = Field(default="1.0", index=True)
    structured_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    parsed_markdown: str
    raw_text_fallback: str | None = None
    extraction_risk: str = Field(default=ExtractionRisk.MEDIUM.value, index=True)
    extraction_model: str | None = None
    verification_model: str | None = None
    source_url: str
    parsed_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True)))
    verified_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class UserJobMatch(TimestampMixin, table=True):
    __tablename__ = "user_job_matches"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job_match"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    job_id: UUID = Field(foreign_key="jobs.id", index=True)
    match_score: float = Field(default=0.0, ge=0.0, le=1.0)
    match_verdict: str = Field(default=MatchVerdict.NEEDS_REVIEW.value, index=True)
    preference_failures: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    missing_requirements: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    adjacent_evidence: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    short_explanation: str = ""
    saved_status: str = Field(default=SavedStatus.NEW.value, index=True)
    application_status: str = Field(default=ApplicationStatus.NOT_STARTED.value, index=True)
    tailoring_status: str = Field(default=TailoringStatus.NOT_STARTED.value, index=True)


class UserProfileItem(TimestampMixin, table=True):
    __tablename__ = "user_profile_items"
    __table_args__ = (UniqueConstraint("user_id", "source_item_id", name="uq_user_profile_source"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    source_item_id: str = Field(index=True)
    kind: str = Field(index=True)
    payload: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    is_active: bool = Field(default=True, index=True)


class TailoringSession(TimestampMixin, table=True):
    __tablename__ = "tailoring_sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    job_id: UUID = Field(foreign_key="jobs.id", index=True)
    job_spec_id: UUID = Field(foreign_key="job_specs.id", index=True)
    status: str = Field(default=TailoringStatus.SELECTION_DRAFT.value, index=True)
    selection_plan: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    confirmed_selection_plan: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    template_plan: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    resume_content: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    revision_notes: str | None = None


class ResumeArtifact(TimestampMixin, table=True):
    __tablename__ = "resume_artifacts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tailoring_session_id: UUID = Field(foreign_key="tailoring_sessions.id", index=True)
    job_id: UUID = Field(foreign_key="jobs.id", index=True)
    user_id: UUID = Field(index=True)
    pdf_path: str | None = None
    tex_path: str | None = None
    log_path: str | None = None
    job_spec_version: int
    selection_plan: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    template_plan: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    resume_content: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    compile_metadata: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    is_final: bool = Field(default=False, index=True)


class ModelRun(TimestampMixin, table=True):
    __tablename__ = "model_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID | None = Field(default=None, index=True)
    job_id: UUID | None = Field(default=None, index=True)
    tailoring_session_id: UUID | None = Field(default=None, index=True)
    stage: str = Field(index=True)
    model_name: str
    prompt_version: str
    input_summary: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    output_summary: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    success: bool = True
    error_message: str | None = None


class CompileRun(TimestampMixin, table=True):
    __tablename__ = "compile_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tailoring_session_id: UUID = Field(foreign_key="tailoring_sessions.id", index=True)
    success: bool
    compiler: str
    tex_path: str | None = None
    pdf_path: str | None = None
    log_path: str | None = None
    page_count: int | None = None
    compiler_output: str = ""
    repair_attempted: bool = False
