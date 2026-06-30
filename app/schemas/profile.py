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

    title: str | None = None
    organization: str | None = None
    description: str
    skills: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    url: str | None = None

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
