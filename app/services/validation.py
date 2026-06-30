from __future__ import annotations

from app.core.enums import ExtractionRisk
from app.core.errors import BlockedWorkflowError
from app.schemas.job_spec import SUPPORTED_JOB_SPEC_VERSION, JobSpec
from app.schemas.resume import ResumeContent, TemplatePlan
from app.schemas.selection import SelectionPlan


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
    too_long = [
        value.placeholder_id
        for value in resume_content.placeholder_values
        if len(value.text.split()) > placeholder_limits[value.placeholder_id]
    ]
    if too_long:
        raise BlockedWorkflowError(f"resume_content exceeds word limits: {sorted(too_long)}")
