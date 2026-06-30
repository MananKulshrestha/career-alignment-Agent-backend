from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import MatchVerdict


class RequirementGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(min_length=1)
    status: str = "not_supported"
    adjacent_evidence_item_ids: list[str] = Field(default_factory=list)
    resume_policy: str = "Keep visible as a gap; do not claim unsupported experience."


class AdjacentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str
    item_ids: list[str] = Field(default_factory=list)
    explanation: str


class MatchAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_score: float = Field(ge=0.0, le=1.0)
    match_verdict: MatchVerdict
    preference_failures: list[str] = Field(default_factory=list)
    missing_requirements: list[RequirementGap] = Field(default_factory=list)
    adjacent_evidence: list[AdjacentEvidence] = Field(default_factory=list)
    short_explanation: str = Field(min_length=1)
