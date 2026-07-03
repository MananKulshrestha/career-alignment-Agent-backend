from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import ResumeLength, StrEnum
from app.schemas.selection import ALLOWED_RESUME_SECTIONS


class ContentType(StrEnum):
    RESUME_BULLET = "resume_bullet"
    SECTION_HEADING = "section_heading"
    SUMMARY = "summary"
    SKILL_LIST = "skill_list"
    DATE_RANGE = "date_range"
    ENTRY_TITLE = "entry_title"
    ENTRY_ORGANIZATION = "entry_organization"
    LOCATION = "location"
    TECH_STACK = "tech_stack"


class ClaimStrength(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    ASSERTIVE = "assertive"


class ResumeWarningType(StrEnum):
    MISSING_REQUIREMENT = "missing_requirement"
    WEAK_EVIDENCE = "weak_evidence"
    USER_REVIEW = "user_review"


class TemplatePlaceholder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    placeholder_id: str = Field(min_length=1)
    source_item_id: str = Field(min_length=1)
    max_words: int = Field(default=24, ge=1, le=80)
    content_type: ContentType
    section: str | None = None
    entry_id: str | None = None
    field_label: str | None = None
    required: bool = True


class LatexRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    escape_special_chars: bool = True
    allow_raw_latex_from_model: bool = False
    ats_readable: bool = True


class TemplatePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_family: Literal["jakes_resume"] = "jakes_resume"
    page_target: ResumeLength = ResumeLength.ONE_PAGE
    section_order: list[str]
    placeholders: list[TemplatePlaceholder] = Field(min_length=1)
    latex_rules: LatexRules = Field(default_factory=LatexRules)

    @field_validator("section_order")
    @classmethod
    def validate_sections(cls, value: list[str]) -> list[str]:
        unknown = set(value) - ALLOWED_RESUME_SECTIONS
        if unknown:
            raise ValueError(f"unknown resume sections: {sorted(unknown)}")
        return value

    @model_validator(mode="after")
    def unique_placeholders(self) -> "TemplatePlan":
        placeholder_ids = [placeholder.placeholder_id for placeholder in self.placeholders]
        if len(placeholder_ids) != len(set(placeholder_ids)):
            raise ValueError("template placeholders cannot contain duplicate placeholder_id values")
        unknown_sections = {
            placeholder.section
            for placeholder in self.placeholders
            if placeholder.section and placeholder.section not in ALLOWED_RESUME_SECTIONS
        }
        if unknown_sections:
            raise ValueError(
                f"template placeholders use unknown sections: {sorted(unknown_sections)}"
            )
        return self


class PlaceholderValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    placeholder_id: str = Field(min_length=1)
    text: str = ""
    source_item_ids: list[str] = Field(default_factory=list)
    claim_strength: ClaimStrength = ClaimStrength.BALANCED

    @field_validator("text")
    @classmethod
    def reject_raw_latex_commands(cls, value: str) -> str:
        blocked = ["\\input", "\\include", "\\write18", "\\usepackage", "\\documentclass"]
        if any(token in value for token in blocked):
            raise ValueError("raw LaTeX structure is not allowed in model content")
        return value.strip()


class ResumeWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ResumeWarningType
    message: str = Field(min_length=1)


class ResumeContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    placeholder_values: list[PlaceholderValue] = Field(min_length=1)
    warnings: list[ResumeWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_placeholders(self) -> "ResumeContent":
        placeholder_ids = [item.placeholder_id for item in self.placeholder_values]
        if len(placeholder_ids) != len(set(placeholder_ids)):
            raise ValueError("placeholder_values cannot contain duplicate placeholder_id values")
        return self


class CompileResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    pdf_path: str | None = None
    tex_path: str | None = None
    html_path: str | None = None
    log_path: str | None = None
    page_count: int | None = None
    compiler_output: str = ""
    repair_attempted: bool = False
