from __future__ import annotations

import re
from typing import Any

from app.core.enums import ExtractionRisk
from app.core.errors import BlockedWorkflowError
from app.schemas.job_spec import SUPPORTED_JOB_SPEC_VERSION, JobSpec
from app.schemas.profile import ProfileItemRead, UserProfileContextRead
from app.schemas.resume import ResumeContent, TemplatePlan
from app.schemas.selection import SelectionPlan

HIGH_RISK_CONTEXT_TERMS = {
    "aws",
    "azure",
    "django",
    "docker",
    "fastapi",
    "flask",
    "gcp",
    "graphql",
    "java",
    "javascript",
    "kubernetes",
    "llm",
    "machine learning",
    "next.js",
    "postgresql",
    "python",
    "react",
    "redis",
    "rest",
    "sql",
    "typescript",
}


def validate_job_spec_handoff(job_spec: JobSpec) -> None:
    if job_spec.schema_version != SUPPORTED_JOB_SPEC_VERSION:
        raise BlockedWorkflowError(
            f"unsupported job_spec schema_version: {job_spec.schema_version}"
        )
    if not job_spec.job_id or not job_spec.title or not job_spec.company:
        raise BlockedWorkflowError("job_spec is missing identity fields")
    if not job_spec.parsed_markdown.strip():
        raise BlockedWorkflowError("job_spec is missing parsed_markdown fallback")
    if (
        job_spec.extraction.risk in {ExtractionRisk.MEDIUM, ExtractionRisk.HIGH}
        and not job_spec.extraction.verified
    ):
        raise BlockedWorkflowError(
            f"{job_spec.extraction.risk.value}-risk extraction must be verified"
        )


def validate_selection_source_ids(
    selection_plan: SelectionPlan, approved_source_ids: set[str]
) -> None:
    unknown: list[str] = []
    for item_ids in selection_plan.selected_item_ids.values():
        unknown.extend(item_id for item_id in item_ids if item_id not in approved_source_ids)
    if unknown:
        raise BlockedWorkflowError(
            f"selection_plan uses unknown profile source IDs: {sorted(set(unknown))}"
        )

    selected_ids = {
        item_id for item_ids in selection_plan.selected_item_ids.values() for item_id in item_ids
    }
    if not selected_ids:
        raise BlockedWorkflowError("selection_plan must include at least one profile source item")
    reason_ids = {reason.item_id for reason in selection_plan.reasons}
    reason_unknown = reason_ids - selected_ids
    if reason_unknown:
        raise BlockedWorkflowError(
            f"selection reasons reference unselected source IDs: {sorted(reason_unknown)}"
        )

    adjacent_unknown = {
        item_id
        for gap in selection_plan.missing_requirements
        for item_id in gap.adjacent_evidence_item_ids
        if item_id not in approved_source_ids
    }
    if adjacent_unknown:
        raise BlockedWorkflowError(
            "missing requirement adjacent evidence uses unknown profile source IDs: "
            f"{sorted(adjacent_unknown)}"
        )


def validate_missing_requirements_preserved(
    draft_selection_plan: SelectionPlan,
    approved_selection_plan: SelectionPlan,
) -> None:
    draft_requirements = {
        gap.requirement.strip().lower() for gap in draft_selection_plan.missing_requirements
    }
    approved_requirements = {
        gap.requirement.strip().lower() for gap in approved_selection_plan.missing_requirements
    }
    removed = draft_requirements - approved_requirements
    if removed:
        raise BlockedWorkflowError(
            f"approved selection must keep missing requirements visible: {sorted(removed)}"
        )


def validate_resume_content(
    template_plan: TemplatePlan,
    resume_content: ResumeContent,
    approved_source_ids: set[str],
) -> None:
    expected_placeholders = {
        placeholder.placeholder_id for placeholder in template_plan.placeholders
    }
    actual_placeholders = {value.placeholder_id for value in resume_content.placeholder_values}
    missing = expected_placeholders - actual_placeholders
    extra = actual_placeholders - expected_placeholders
    if missing:
        raise BlockedWorkflowError(f"resume_content is missing placeholders: {sorted(missing)}")
    if extra:
        raise BlockedWorkflowError(f"resume_content contains unknown placeholders: {sorted(extra)}")

    unknown_sources = {
        source_id
        for value in resume_content.placeholder_values
        for source_id in value.source_item_ids
        if source_id not in approved_source_ids
    }
    if unknown_sources:
        raise BlockedWorkflowError(
            f"resume_content uses unapproved profile source IDs: {sorted(unknown_sources)}"
        )

    placeholder_sources = {
        placeholder.placeholder_id: placeholder.source_item_id
        for placeholder in template_plan.placeholders
    }
    missing_direct_source = [
        value.placeholder_id
        for value in resume_content.placeholder_values
        if placeholder_sources[value.placeholder_id] not in value.source_item_ids
    ]
    if missing_direct_source:
        raise BlockedWorkflowError(
            "resume_content must cite each placeholder's source item ID: "
            f"{sorted(missing_direct_source)}"
        )

    placeholder_limits = {
        placeholder.placeholder_id: placeholder.max_words
        for placeholder in template_plan.placeholders
    }
    required_placeholders = {
        placeholder.placeholder_id
        for placeholder in template_plan.placeholders
        if placeholder.required
    }
    empty_required = [
        value.placeholder_id
        for value in resume_content.placeholder_values
        if value.placeholder_id in required_placeholders and not value.text.strip()
    ]
    if empty_required:
        raise BlockedWorkflowError(
            f"resume_content contains empty required placeholders: {sorted(empty_required)}"
        )

    too_long = [
        value.placeholder_id
        for value in resume_content.placeholder_values
        if len(value.text.split()) > placeholder_limits[value.placeholder_id]
    ]
    if too_long:
        raise BlockedWorkflowError(f"resume_content exceeds word limits: {sorted(too_long)}")


def validate_user_context_constraints(
    resume_content: ResumeContent,
    approved_profile_items: list[ProfileItemRead],
    user_context: UserProfileContextRead | None,
) -> None:
    if not user_context:
        return

    profile_by_source_id = {item.source_item_id: item for item in approved_profile_items}
    context_terms = _context_only_terms(user_context)
    avoided_terms = _avoid_claim_terms(user_context)

    for value in resume_content.placeholder_values:
        text = value.text
        if not text.strip():
            continue
        cited_evidence_text = " ".join(
            _profile_item_evidence_text(profile_by_source_id[source_id])
            for source_id in value.source_item_ids
            if source_id in profile_by_source_id
        )
        for term in context_terms:
            if _contains_term(text, term) and not _contains_term(cited_evidence_text, term):
                raise BlockedWorkflowError(
                    f"resume_content uses context-only claim {term!r} in {value.placeholder_id}"
                )
        for term in avoided_terms:
            if _contains_term(text, term):
                raise BlockedWorkflowError(
                    f"resume_content uses avoided claim {term!r} in {value.placeholder_id}"
                )


def _context_only_terms(user_context: UserProfileContextRead) -> set[str]:
    terms = {
        _normalize_term(value)
        for value in [
            *user_context.specializations,
            *user_context.career_goals,
            *user_context.target_roles,
        ]
        if _normalize_term(value)
    }
    abstract = user_context.abstract or ""
    abstract_lower = abstract.lower()
    for term in HIGH_RISK_CONTEXT_TERMS:
        if _contains_term(abstract_lower, term):
            terms.add(term)
    return terms


def _avoid_claim_terms(user_context: UserProfileContextRead) -> set[str]:
    terms = {
        _normalize_term(value) for value in user_context.avoid_claims if _normalize_term(value)
    }
    leadership_terms = {"lead", "leader", "leaders", "leading", "leadership", "led"}
    if terms & leadership_terms or "leadership" in terms:
        terms.update(leadership_terms)
    return terms


def _profile_item_evidence_text(item: ProfileItemRead) -> str:
    return " ".join(_flatten_strings(item.payload.model_dump(mode="json"))).lower()


def _flatten_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        results: list[str] = []
        for item in value:
            results.extend(_flatten_strings(item))
        return results
    if isinstance(value, dict):
        results = []
        for item in value.values():
            results.extend(_flatten_strings(item))
        return results
    return [str(value)]


def _normalize_term(value: str) -> str:
    return " ".join(value.lower().split())


def _contains_term(text: str, term: str) -> bool:
    normalized_text = text.lower()
    normalized_term = _normalize_term(term)
    if not normalized_term:
        return False
    escaped = re.escape(normalized_term).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", normalized_text) is not None
