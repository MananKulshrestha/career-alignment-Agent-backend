from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import ResumeLength, StrEnum

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
    "certifications",
]


class RequirementSupportStatus(StrEnum):
    SUPPORTED = "supported"
    ADJACENT = "adjacent"
    NOT_SUPPORTED = "not_supported"
    NEEDS_USER_INPUT = "needs_user_input"


class ImprovementSuggestionSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class ImprovementSuggestionCategory(StrEnum):
    MISSING_METRIC = "missing_metric"
    MISSING_DATE = "missing_date"
    MISSING_LINK = "missing_link"
    WEAK_KEYWORD_COVERAGE = "weak_keyword_coverage"
    UNSUPPORTED_REQUIREMENT = "unsupported_requirement"
    UNCLEAR_OWNERSHIP = "unclear_ownership"
    VAGUE_IMPACT = "vague_impact"
    OTHER = "other"


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


class SectionEntrySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_item_id: str = Field(min_length=1)
    bullet_count: int | None = Field(default=None, ge=0, le=6)
    selection_reason: str | None = Field(default=None, max_length=400)


class ResumeImprovementSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: ImprovementSuggestionSeverity = ImprovementSuggestionSeverity.INFO
    category: ImprovementSuggestionCategory = ImprovementSuggestionCategory.OTHER
    message: str = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=500)
    source_item_id: str | None = None
    requirement: str | None = None


class SelectionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_family: Literal["jakes_resume"] = "jakes_resume"
    section_order: list[ResumeSection] = Field(default_factory=list)
    page_target: ResumeLength = ResumeLength.ONE_PAGE
    selected_item_ids: dict[ResumeSection, list[str]] = Field(default_factory=dict)
    selected_entries: dict[ResumeSection, list[SectionEntrySelection]] = Field(default_factory=dict)
    reasons: list[SelectionReason] = Field(default_factory=list)
    target_keywords_covered: list[str] = Field(default_factory=list)
    missing_requirements: list[MissingRequirement] = Field(default_factory=list)
    user_improvement_suggestions: list[ResumeImprovementSuggestion] = Field(default_factory=list)

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

        unknown_entries = set(self.selected_entries) - ALLOWED_RESUME_SECTIONS
        if unknown_entries:
            raise ValueError(
                f"selected_entries contains unknown sections: {sorted(unknown_entries)}"
            )

        selected_sections = {
            section for section, item_ids in self.selected_item_ids.items() if item_ids
        }
        entry_sections = {section for section, entries in self.selected_entries.items() if entries}
        missing_from_order = (selected_sections | entry_sections) - set(self.section_order)
        if missing_from_order:
            raise ValueError(
                f"selected sections must be present in section_order: {sorted(missing_from_order)}"
            )

        if not self.selected_entries and self.selected_item_ids:
            self.selected_entries = {
                section: [
                    SectionEntrySelection(
                        source_item_id=source_item_id,
                        bullet_count=_default_bullet_count(section),
                    )
                    for source_item_id in source_ids
                ]
                for section, source_ids in self.selected_item_ids.items()
                if source_ids
            }
        elif self.selected_entries and not self.selected_item_ids:
            self.selected_item_ids = {
                section: [entry.source_item_id for entry in entries]
                for section, entries in self.selected_entries.items()
                if entries
            }
        elif self.selected_entries and self.selected_item_ids:
            for section, entries in self.selected_entries.items():
                entry_ids = [entry.source_item_id for entry in entries]
                selected_ids = self.selected_item_ids.get(section, [])
                if entry_ids != selected_ids:
                    raise ValueError(
                        "selected_entries and selected_item_ids disagree for "
                        f"{section}: {entry_ids} != {selected_ids}"
                    )

        for section, entries in self.selected_entries.items():
            entry_ids = [entry.source_item_id for entry in entries]
            if len(entry_ids) != len(set(entry_ids)):
                raise ValueError(f"duplicate source_item_id values in {section}")
            for entry in entries:
                if entry.bullet_count is None:
                    entry.bullet_count = _default_bullet_count(section)

        return self


class SelectionApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_plan: SelectionPlan
    approved_by_user: bool
    user_notes: str | None = None


def _default_bullet_count(section: str) -> int:
    if section in {"experience", "projects"}:
        return 2
    if section in {"achievements", "certifications", "summary"}:
        return 1
    return 0
