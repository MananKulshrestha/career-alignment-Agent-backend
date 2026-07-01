from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.core.enums import ExtractionRisk, RequirementType
from app.core.errors import BlockedWorkflowError
from app.schemas.job_spec import ExtractionMetadata, JobSpec, SkillRequirement, TextRequirement
from app.schemas.resume import (
    ContentType,
    PlaceholderValue,
    ResumeContent,
    TemplatePlaceholder,
    TemplatePlan,
)
from app.schemas.selection import (
    MissingRequirement,
    RequirementSupportStatus,
    SectionEntrySelection,
    SelectionPlan,
    SelectionReason,
)
from app.services.fallbacks import fallback_job_spec
from app.services.url_normalizer import canonicalize_url
from app.services.validation import (
    validate_job_spec_handoff,
    validate_missing_requirements_preserved,
    validate_resume_content,
    validate_selection_source_ids,
)


def test_fallback_job_spec_is_valid_and_verified() -> None:
    spec = fallback_job_spec(
        source_url="manual://sample",
        text=(
            "Backend Engineer at ExampleCo\n"
            "Company: ExampleCo\n"
            "Build Python FastAPI services with PostgreSQL and Docker. "
            "Own API reliability and collaborate with frontend teams."
        ),
    )

    validate_job_spec_handoff(spec)
    assert spec.title == "Backend Engineer"
    assert spec.company == "ExampleCo"
    assert spec.extraction.verified is True
    assert {skill.name for skill in spec.required_skills} >= {"Python", "FastAPI", "PostgreSQL"}


def test_job_spec_rejects_empty_required_arrays() -> None:
    with pytest.raises(ValidationError):
        JobSpec(
            job_id="job_1",
            source_url="manual://bad",
            title="Engineer",
            company="ExampleCo",
            required_skills=[],
            responsibilities=[
                TextRequirement(text="Build reliable APIs.", confidence=0.8),
            ],
            qualifications=[
                TextRequirement(text="Experience with backend systems.", confidence=0.8),
            ],
            extraction=ExtractionMetadata(
                risk=ExtractionRisk.LOW,
                model="test",
                verified=True,
                parsed_at=datetime.now(timezone.utc),
            ),
            parsed_markdown="A job posting",
        )


def test_low_risk_job_spec_must_be_verified() -> None:
    with pytest.raises(ValidationError):
        JobSpec(
            job_id="job_1",
            source_url="manual://bad",
            title="Engineer",
            company="ExampleCo",
            required_skills=[
                SkillRequirement(name="Python", requirement_type=RequirementType.EXPLICIT),
            ],
            responsibilities=[
                TextRequirement(text="Build reliable APIs.", confidence=0.8),
            ],
            qualifications=[
                TextRequirement(text="Experience with backend systems.", confidence=0.8),
            ],
            extraction=ExtractionMetadata(
                risk=ExtractionRisk.LOW,
                model="test",
                verified=False,
                parsed_at=datetime.now(timezone.utc),
            ),
            parsed_markdown="A job posting",
        )


def test_selection_plan_rejects_unknown_sections() -> None:
    with pytest.raises(ValidationError):
        SelectionPlan(
            section_order=["experience", "made_up_section"],
            selected_item_ids={"experience": ["exp_1"]},
        )


def test_selection_plan_requires_selected_sections_in_order() -> None:
    with pytest.raises(ValidationError):
        SelectionPlan(
            section_order=["experience"],
            selected_item_ids={"projects": ["project_1"]},
        )


def test_selection_plan_rejects_impossible_bullet_counts() -> None:
    with pytest.raises(ValidationError):
        SelectionPlan(
            section_order=["projects"],
            selected_item_ids={"projects": ["project_1"]},
            selected_entries={
                "projects": [
                    SectionEntrySelection(source_item_id="project_1", bullet_count=7),
                ]
            },
        )


def test_selection_plan_rejects_selected_entry_id_mismatch() -> None:
    with pytest.raises(ValidationError):
        SelectionPlan(
            section_order=["projects"],
            selected_item_ids={"projects": ["project_1"]},
            selected_entries={
                "projects": [
                    SectionEntrySelection(source_item_id="project_2", bullet_count=1),
                ]
            },
        )


def test_selection_validation_rejects_empty_selection() -> None:
    plan = SelectionPlan(section_order=["projects"], selected_item_ids={})

    with pytest.raises(BlockedWorkflowError):
        validate_selection_source_ids(plan, {"project_1"})


def test_selection_validation_rejects_unselected_reason_ids() -> None:
    plan = SelectionPlan(
        section_order=["projects"],
        selected_item_ids={"projects": ["project_1"]},
        reasons=[SelectionReason(item_id="project_2", reason="Not selected.")],
    )

    with pytest.raises(BlockedWorkflowError):
        validate_selection_source_ids(plan, {"project_1", "project_2"})


def test_approval_must_preserve_missing_requirements() -> None:
    draft = SelectionPlan(
        section_order=["projects"],
        selected_item_ids={"projects": ["project_1"]},
        missing_requirements=[
            MissingRequirement(
                requirement="Kubernetes",
                status=RequirementSupportStatus.NOT_SUPPORTED,
                resume_policy="Do not claim Kubernetes.",
            )
        ],
    )
    approved = SelectionPlan(
        section_order=["projects"],
        selected_item_ids={"projects": ["project_1"]},
        missing_requirements=[],
    )

    with pytest.raises(BlockedWorkflowError):
        validate_missing_requirements_preserved(draft, approved)


def test_resume_content_must_cite_placeholder_source() -> None:
    template = TemplatePlan(
        section_order=["projects"],
        placeholders=[
            TemplatePlaceholder(
                placeholder_id="projects_project_1_bullet_1",
                source_item_id="project_1",
                max_words=12,
                content_type=ContentType.RESUME_BULLET,
            )
        ],
    )
    content = ResumeContent(
        placeholder_values=[
            PlaceholderValue(
                placeholder_id="projects_project_1_bullet_1",
                text="Built reliable APIs.",
                source_item_ids=["project_2"],
            )
        ]
    )

    with pytest.raises(BlockedWorkflowError):
        validate_resume_content(template, content, {"project_1", "project_2"})


def test_resume_content_rejects_extra_placeholders() -> None:
    template = TemplatePlan(
        section_order=["projects"],
        placeholders=[
            TemplatePlaceholder(
                placeholder_id="projects_project_1_bullet_1",
                source_item_id="project_1",
                max_words=12,
                content_type=ContentType.RESUME_BULLET,
            )
        ],
    )
    content = ResumeContent(
        placeholder_values=[
            PlaceholderValue(
                placeholder_id="projects_project_1_bullet_1",
                text="Built reliable APIs.",
                source_item_ids=["project_1"],
            ),
            PlaceholderValue(
                placeholder_id="certifications_fake_cert_title",
                text="AWS Certified Solutions Architect",
                source_item_ids=["project_1"],
            ),
        ]
    )

    with pytest.raises(BlockedWorkflowError):
        validate_resume_content(template, content, {"project_1"})


def test_resume_content_rejects_empty_required_placeholder() -> None:
    template = TemplatePlan(
        section_order=["projects"],
        placeholders=[
            TemplatePlaceholder(
                placeholder_id="projects_project_1_name",
                source_item_id="project_1",
                content_type=ContentType.ENTRY_TITLE,
                required=True,
            ),
            TemplatePlaceholder(
                placeholder_id="projects_project_1_dates",
                source_item_id="project_1",
                content_type=ContentType.DATE_RANGE,
                required=False,
            ),
        ],
    )
    content = ResumeContent(
        placeholder_values=[
            PlaceholderValue(
                placeholder_id="projects_project_1_name",
                text="",
                source_item_ids=["project_1"],
            ),
            PlaceholderValue(
                placeholder_id="projects_project_1_dates",
                text="",
                source_item_ids=["project_1"],
            ),
        ]
    )

    with pytest.raises(BlockedWorkflowError):
        validate_resume_content(template, content, {"project_1"})


def test_resume_content_allows_empty_optional_placeholder() -> None:
    template = TemplatePlan(
        section_order=["projects"],
        placeholders=[
            TemplatePlaceholder(
                placeholder_id="projects_project_1_name",
                source_item_id="project_1",
                content_type=ContentType.ENTRY_TITLE,
            ),
            TemplatePlaceholder(
                placeholder_id="projects_project_1_dates",
                source_item_id="project_1",
                content_type=ContentType.DATE_RANGE,
                required=False,
            ),
        ],
    )
    content = ResumeContent(
        placeholder_values=[
            PlaceholderValue(
                placeholder_id="projects_project_1_name",
                text="Backend Tracker",
                source_item_ids=["project_1"],
            ),
            PlaceholderValue(
                placeholder_id="projects_project_1_dates",
                text="",
                source_item_ids=["project_1"],
            ),
        ]
    )

    validate_resume_content(template, content, {"project_1"})


def test_template_and_resume_content_require_placeholders() -> None:
    with pytest.raises(ValidationError):
        TemplatePlan(section_order=["projects"], placeholders=[])

    with pytest.raises(ValidationError):
        ResumeContent(placeholder_values=[])


def test_canonicalize_url_accepts_bare_domain_and_rejects_non_http() -> None:
    assert (
        canonicalize_url("example.com/jobs/123?utm_source=newsletter&b=2&a=1")
        == "https://example.com/jobs/123?a=1&b=2"
    )

    with pytest.raises(BlockedWorkflowError):
        canonicalize_url("javascript:alert(1)")
