from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import ResumeLength, StrEnum

from typing import Literal

ALLOWED_RESUME_SECTIONS = {
    "summary",
    "education",
    "experience",
    "projects",
    "technical_skills",
    "achievements",
    "certifications",
}

ResumeSection = Literal[
    "summary",
    "education",
    "experience",
    "projects",
    "technical_skills",
    "achievements",
    "certifications"
]


class RequirementSupportStatus(StrEnum):
    SUPPORTED = "supported"
    ADJACENT = "adjacent"
    NOT_SUPPORTED = "not_supported"
    NEEDS_USER_INPUT = "needs_user_input"


class SelectionReason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    reason: str = Field(min_length=1, max_length=400)


class MissingRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(min_length=1)
    status: RequirementSupportStatus
    adjacent_evidence_item_ids: list[str] = Field(default_factory=list)
    resume_policy: str = Field(min_length=1)


class SelectionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_order: list[ResumeSection] = Field(default_factory=list)
    page_target: ResumeLength = ResumeLength.ONE_PAGE
    selected_item_ids: dict[ResumeSection, list[str]] = Field(default_factory=dict)
    reasons: list[SelectionReason] = Field(default_factory=list)
    target_keywords_covered: list[str] = Field(default_factory=list)
    missing_requirements: list[MissingRequirement] = Field(default_factory=list)

    @field_validator("section_order")
    @classmethod
    def validate_sections(cls, value: list[str]) -> list[str]:
        unknown = set(value) - ALLOWED_RESUME_SECTIONS
        if unknown:
            raise ValueError(f"unknown resume sections: {sorted(unknown)}")
        # Auto-fix: remove duplicates while preserving order
        seen = set()
        deduped = []
        for v in value:
            if v not in seen:
                seen.add(v)
                deduped.append(v)
        return deduped

    @model_validator(mode="after")
    def ensure_selected_sections_are_allowed(self) -> "SelectionPlan":
        unknown = set(self.selected_item_ids) - ALLOWED_RESUME_SECTIONS
        if unknown:
            raise ValueError(f"selected_item_ids contains unknown sections: {sorted(unknown)}")
        
        # Auto-fix: if the LLM selected items for a section but forgot to add it to section_order, just append it
        for section, item_ids in self.selected_item_ids.items():
            if item_ids and section not in self.section_order:
                self.section_order.append(section)
                
        return self


class SelectionApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_plan: SelectionPlan
    approved_by_user: bool
    user_notes: str | None = None
