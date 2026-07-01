from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import StrEnum


class ProfileItemKind(StrEnum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    PROJECT = "project"
    ACHIEVEMENT = "achievement"
    CERTIFICATION = "certification"
    EDUCATION = "education"
    RESEARCH_NOTE = "research_note"
    PREFERENCE = "preference"


class EvidenceGapStatus(StrEnum):
    MISSING = "missing"
    ANSWERED = "answered"
    NOT_APPLICABLE = "not_applicable"


class EvidenceGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(min_length=1)
    question: str = Field(min_length=1)
    status: EvidenceGapStatus = EvidenceGapStatus.MISSING
    answer: str | None = None


class UserPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    desired_titles: list[str] = Field(default_factory=list)
    desired_locations: list[str] = Field(default_factory=list)
    remote_policies: list[str] = Field(default_factory=list)
    minimum_salary: float | None = None
    hard_requirements: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    match_threshold: float = Field(default=0.65, ge=0.0, le=1.0)


class ProfileItemPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Common fields retained for compatibility with the existing API.
    title: str | None = None
    organization: str | None = None
    description: str
    skills: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    url: str | None = None
    location: str | None = None

    # Project-specific evidence.
    problem: str | None = None
    target_users: str | None = None
    role: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    architecture: str | None = None
    features: list[str] = Field(default_factory=list)
    measurable_impact: str | None = None
    repo_url: str | None = None
    demo_url: str | None = None
    collaboration: str | None = None
    constraints_tradeoffs: str | None = None

    # Experience-specific evidence.
    employer: str | None = None
    job_title: str | None = None
    employment_type: str | None = None
    team_scope: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    promotions_ownership: str | None = None
    cross_functional_work: str | None = None

    # Education-specific evidence.
    school: str | None = None
    degree: str | None = None
    coursework: list[str] = Field(default_factory=list)
    gpa: str | None = None
    honors: list[str] = Field(default_factory=list)

    # Skill-specific evidence.
    skill_category: str | None = None
    proficiency: str | None = None
    evidence_source: str | None = None

    # Achievement/certification evidence.
    issuer: str | None = None
    criteria: str | None = None
    ranking_score: str | None = None
    credential_url: str | None = None
    credential_date: date | None = None

    # Research-note evidence.
    research_topic: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    relevance: str | None = None
    limitations: str | None = None

    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def description_must_have_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description cannot be empty")
        return value.strip()


class ProfileItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ProfileItemKind
    source_item_id: str = Field(min_length=1)
    payload: ProfileItemPayload
    is_active: bool = True


class ProfileItemRead(ProfileItemCreate):
    id: str
    user_id: str


class UserProfileRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    preferences: UserPreference = Field(default_factory=UserPreference)
    items: list[ProfileItemRead] = Field(default_factory=list)
