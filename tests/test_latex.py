from app.schemas.resume import (
    ContentType,
    PlaceholderValue,
    ResumeContent,
    TemplatePlaceholder,
    TemplatePlan,
)
from app.services.latex import assemble_latex, escape_latex


def test_escape_latex_special_characters() -> None:
    value = r"Built API_1 with 99% reliability & $0 downtime #core {safe}"

    escaped = escape_latex(value)

    assert r"API\_1" in escaped
    assert r"99\%" in escaped
    assert r"\&" in escaped
    assert r"\$0" in escaped
    assert r"\#core" in escaped
    assert r"\{safe\}" in escaped


def test_assemble_latex_uses_jakes_resume_commands() -> None:
    source_item_id = "project_backend_tracker"
    template_plan = TemplatePlan(
        section_order=["projects"],
        placeholders=[
            TemplatePlaceholder(
                placeholder_id="projects_project_backend_tracker_name",
                source_item_id=source_item_id,
                content_type=ContentType.ENTRY_TITLE,
                section="projects",
                entry_id="projects_project_backend_tracker",
            ),
            TemplatePlaceholder(
                placeholder_id="projects_project_backend_tracker_tech_stack",
                source_item_id=source_item_id,
                content_type=ContentType.TECH_STACK,
                section="projects",
                entry_id="projects_project_backend_tracker",
                required=False,
            ),
            TemplatePlaceholder(
                placeholder_id="projects_project_backend_tracker_dates",
                source_item_id=source_item_id,
                content_type=ContentType.DATE_RANGE,
                section="projects",
                entry_id="projects_project_backend_tracker",
                required=False,
            ),
            TemplatePlaceholder(
                placeholder_id="projects_project_backend_tracker_bullet_1",
                source_item_id=source_item_id,
                content_type=ContentType.RESUME_BULLET,
                section="projects",
                entry_id="projects_project_backend_tracker",
            ),
        ],
    )
    content = ResumeContent(
        placeholder_values=[
            PlaceholderValue(
                placeholder_id="projects_project_backend_tracker_name",
                text="Backend Job Tracker",
                source_item_ids=[source_item_id],
            ),
            PlaceholderValue(
                placeholder_id="projects_project_backend_tracker_tech_stack",
                text="FastAPI, PostgreSQL",
                source_item_ids=[source_item_id],
            ),
            PlaceholderValue(
                placeholder_id="projects_project_backend_tracker_dates",
                text="Jan 2026 -- Present",
                source_item_ids=[source_item_id],
            ),
            PlaceholderValue(
                placeholder_id="projects_project_backend_tracker_bullet_1",
                text="Built API_1 with 99% reliability.",
                source_item_ids=[source_item_id],
            ),
        ]
    )

    latex = assemble_latex(
        template_plan=template_plan,
        resume_content=content,
        profile_items=[],
    )

    assert r"\documentclass[letterpaper,11pt]{article}" in latex
    assert r"\resumeProjectHeading" in latex
    assert r"\resumeItem{Built API\_1 with 99\% reliability.}" in latex
    assert r"\pdfgentounicode=1" in latex
