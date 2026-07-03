from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import (
    ExtractionRisk,
    FileType,
    RemotePolicy,
    RequirementType,
    ResumeLength,
    SalaryPeriod,
    Seniority,
)

SUPPORTED_JOB_SPEC_VERSION = "1.0"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_section: str | None = None
    source_snippet: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SkillRequirement(Evidence):
    name: str = Field(min_length=1)
    requirement_type: RequirementType = RequirementType.EXPLICIT


class TextRequirement(Evidence):
    text: str = Field(min_length=1)
    requirement_type: RequirementType = RequirementType.EXPLICIT


class JobConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_length: ResumeLength = ResumeLength.UNSPECIFIED
    file_type: FileType = FileType.UNSPECIFIED
    location_restrictions: list[str] = Field(default_factory=list)


class JobSalary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float | None = None
    max: float | None = None
    currency: str | None = None
    period: SalaryPeriod = SalaryPeriod.UNKNOWN

    @model_validator(mode="after")
    def validate_salary_bounds(self) -> "JobSalary":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("salary.min cannot be greater than salary.max")
        return self


class ExtractionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk: ExtractionRisk
    model: str
    verified: bool = False
    parsed_at: datetime


class JobSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    schema_version: Literal["1.0"] = SUPPORTED_JOB_SPEC_VERSION
    source_url: str
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    location: str | None = None
    remote_policy: RemotePolicy = RemotePolicy.UNKNOWN
    seniority: Seniority = Seniority.UNKNOWN
    required_skills: list[SkillRequirement] = Field(default_factory=list, validate_default=True)
    nice_to_have_skills: list[SkillRequirement] = Field(default_factory=list)
    responsibilities: list[TextRequirement] = Field(default_factory=list, validate_default=True)
    qualifications: list[TextRequirement] = Field(default_factory=list, validate_default=True)
    ats_keywords: list[str] = Field(default_factory=list)
    company_domain_context: list[str] = Field(default_factory=list)
    constraints: JobConstraints = Field(default_factory=JobConstraints)
    application_deadline: str | None = None
    salary: JobSalary = Field(default_factory=JobSalary)
    extraction: ExtractionMetadata
    parsed_markdown: str = Field(min_length=1)
    raw_text_fallback: str | None = None

    @field_validator("ats_keywords", "company_domain_context", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @model_validator(mode="after")
    def ensure_verified_when_low_risk(self) -> "JobSpec":
        if not self.required_skills:
            raise ValueError("job_specs must include at least one required skill")
        if not self.responsibilities:
            raise ValueError("job_specs must include at least one responsibility")
        if not self.qualifications:
            raise ValueError("job_specs must include at least one qualification")
        if self.extraction.risk == ExtractionRisk.LOW and not self.extraction.verified:
            raise ValueError(
                "low-risk job_specs must still be marked verified by deterministic validation"
            )
        return self


class JobSpecEnvelope(BaseModel):
    """Stored job spec plus version metadata."""

    model_config = ConfigDict(extra="forbid")

    version: int
    job_spec: JobSpec
