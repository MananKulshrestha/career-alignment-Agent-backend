from uuid import uuid4

from app.core.config import settings
from app.schemas.profile import ProfileItemKind, ProfileItemPayload, ProfileItemRead
from app.schemas.resume import (
    ContentType,
    PlaceholderValue,
    ResumeContent,
    TemplatePlaceholder,
    TemplatePlan,
)
from app.services.latex import assemble_latex, compile_resume, escape_latex


def test_escape_latex_special_characters() -> None:
    value = r"Built API_1 with 99% reliability & $0 downtime #core {safe}"

    escaped = escape_latex(value)

    assert r"API\_1" in escaped
    assert r"99\%" in escaped
    assert r"\&" in escaped
    assert r"\$0" in escaped
    assert r"\#core" in escaped
    assert r"\{safe\}" in escaped


def test_compile_resume_falls_back_when_latex_engine_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "artifacts_dir", tmp_path)
    monkeypatch.setattr(settings, "latex_engine", "definitely_missing_pdflatex")
    source_item_id = "project_backend_tracker"
    placeholder_id = "projects_project_backend_tracker_bullet_1"

    result = compile_resume(
        session_id=uuid4(),
        template_plan=TemplatePlan(
            section_order=["projects"],
            placeholders=[
                TemplatePlaceholder(
                    placeholder_id=placeholder_id,
                    source_item_id=source_item_id,
                    content_type=ContentType.RESUME_BULLET,
                )
            ],
        ),
        resume_content=ResumeContent(
            placeholder_values=[
                PlaceholderValue(
                    placeholder_id=placeholder_id,
                    text="Built reliable FastAPI services with PostgreSQL persistence.",
                    source_item_ids=[source_item_id],
                )
            ]
        ),
        profile_items=[
            ProfileItemRead(
                id="profile_1",
                user_id="user_1",
                kind=ProfileItemKind.PROJECT,
                source_item_id=source_item_id,
                payload=ProfileItemPayload(
                    title="Backend Job Tracker",
                    description="Built a backend job tracker.",
                    skills=["FastAPI", "PostgreSQL"],
                ),
            )
        ],
    )

    assert result.success is True
    assert result.pdf_path is not None
    assert result.page_count == 1
    assert "fallback renderer" in result.compiler_output
    assert result.tex_path is not None
    assert result.log_path is not None
    assert result.pdf_path.endswith("resume.pdf")
    with open(result.pdf_path, "rb") as pdf_file:
        pdf_bytes = pdf_file.read()
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"/Times-Bold" in pdf_bytes
    assert b"/Times-Italic" in pdf_bytes
    assert b"(Candidate Name)" in pdf_bytes
    assert b" l S" in pdf_bytes
    with open(result.log_path, encoding="utf-8") as log_file:
        assert "Jake-style" in log_file.read()


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
