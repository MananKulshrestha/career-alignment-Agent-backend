import subprocess
from uuid import uuid4

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.models.tables import (
    CompileRun,
    JobSpecRecord,
    ResumeArtifact,
    TailoringSession,
    UserProfileItem,
)
from app.schemas.profile import ProfileItemKind, ProfileItemPayload, ProfileItemRead
from app.schemas.resume import (
    CompileResult,
    ContentType,
    PlaceholderValue,
    ResumeContent,
    TemplatePlaceholder,
    TemplatePlan,
)
from app.schemas.selection import SelectionPlan
from app.services import html_renderer, tailoring
from app.services.html_renderer import HTML_RENDERER_NAME, build_template_context, compile_resume


def test_build_template_context_groups_sections_and_profile_links() -> None:
    template_plan = TemplatePlan(
        section_order=[
            "summary",
            "education",
            "experience",
            "projects",
            "technical_skills",
            "certifications",
        ],
        placeholders=[
            _placeholder("summary_summary_1_summary", "summary_1", ContentType.SUMMARY, "summary"),
            _placeholder(
                "education_edu_1_school",
                "edu_1",
                ContentType.ENTRY_ORGANIZATION,
                "education",
                "education_edu_1",
            ),
            _placeholder(
                "education_edu_1_degree",
                "edu_1",
                ContentType.ENTRY_TITLE,
                "education",
                "education_edu_1",
            ),
            _placeholder(
                "education_edu_1_location",
                "edu_1",
                ContentType.LOCATION,
                "education",
                "education_edu_1",
                required=False,
            ),
            _placeholder(
                "education_edu_1_dates",
                "edu_1",
                ContentType.DATE_RANGE,
                "education",
                "education_edu_1",
                required=False,
            ),
            _placeholder(
                "experience_exp_1_title",
                "exp_1",
                ContentType.ENTRY_TITLE,
                "experience",
                "experience_exp_1",
            ),
            _placeholder(
                "experience_exp_1_organization",
                "exp_1",
                ContentType.ENTRY_ORGANIZATION,
                "experience",
                "experience_exp_1",
                required=False,
            ),
            _placeholder(
                "experience_exp_1_dates",
                "exp_1",
                ContentType.DATE_RANGE,
                "experience",
                "experience_exp_1",
                required=False,
            ),
            _placeholder(
                "experience_exp_1_bullet_1",
                "exp_1",
                ContentType.RESUME_BULLET,
                "experience",
                "experience_exp_1",
            ),
            _placeholder(
                "projects_project_1_name",
                "project_1",
                ContentType.ENTRY_TITLE,
                "projects",
                "projects_project_1",
            ),
            _placeholder(
                "projects_project_1_tech_stack",
                "project_1",
                ContentType.TECH_STACK,
                "projects",
                "projects_project_1",
                required=False,
            ),
            _placeholder(
                "projects_project_1_dates",
                "project_1",
                ContentType.DATE_RANGE,
                "projects",
                "projects_project_1",
                required=False,
            ),
            _placeholder(
                "projects_project_1_bullet_1",
                "project_1",
                ContentType.RESUME_BULLET,
                "projects",
                "projects_project_1",
            ),
            _placeholder(
                "technical_skills_skills_1_skill_list",
                "skills_1",
                ContentType.SKILL_LIST,
                "technical_skills",
                "technical_skills_skills_1",
                field_label="Languages",
            ),
            _placeholder(
                "certifications_cert_1_title",
                "cert_1",
                ContentType.ENTRY_TITLE,
                "certifications",
                "certifications_cert_1",
            ),
            _placeholder(
                "certifications_cert_1_organization",
                "cert_1",
                ContentType.ENTRY_ORGANIZATION,
                "certifications",
                "certifications_cert_1",
                required=False,
            ),
        ],
    )
    resume_content = ResumeContent(
        placeholder_values=[
            _value(
                "summary_summary_1_summary",
                "Backend engineer focused on reliable APIs.",
                "summary_1",
            ),
            _value("education_edu_1_school", "Southwestern University", "edu_1"),
            _value("education_edu_1_degree", "B.A. Computer Science", "edu_1"),
            _value("education_edu_1_location", "Georgetown, TX", "edu_1"),
            _value("education_edu_1_dates", "Aug. 2018 -- May 2021", "edu_1"),
            _value("experience_exp_1_title", "Research Assistant", "exp_1"),
            _value("experience_exp_1_organization", "Texas A&M University", "exp_1"),
            _value("experience_exp_1_dates", "June 2020 -- Present", "exp_1"),
            _value("experience_exp_1_bullet_1", "Built FastAPI services.", "exp_1"),
            _value("projects_project_1_name", "Backend Tracker", "project_1"),
            _value("projects_project_1_tech_stack", "Python, FastAPI", "project_1"),
            _value("projects_project_1_dates", "Jan 2026", "project_1"),
            _value("projects_project_1_bullet_1", "Built a reliable job tracker.", "project_1"),
            _value("technical_skills_skills_1_skill_list", "Python, SQL", "skills_1"),
            _value("certifications_cert_1_title", "AWS Cloud Practitioner", "cert_1"),
            _value("certifications_cert_1_organization", "AWS", "cert_1"),
        ]
    )

    context = build_template_context(
        template_plan=template_plan,
        resume_content=resume_content,
        profile_items=[
            _profile_item(
                "project_1",
                ProfileItemKind.PROJECT,
                repo_url="https://github.com/me/repo",
                demo_url="https://demo.example.com",
            ),
            _profile_item(
                "cert_1",
                ProfileItemKind.CERTIFICATION,
                credential_url="https://verify.example.com/cert",
            ),
        ],
    )

    assert context["section_order"] == template_plan.section_order
    assert context["sections"]["summary"]["paragraphs"] == [
        "Backend engineer focused on reliable APIs."
    ]
    assert context["sections"]["education"]["entries"][0]["organization"] == (
        "Southwestern University"
    )
    assert context["sections"]["experience"]["entries"][0]["bullets"] == [
        "Built FastAPI services."
    ]
    assert context["sections"]["technical_skills"]["skills"] == [
        {"label": "Languages", "items": "Python, SQL"}
    ]
    assert context["sections"]["projects"]["entries"][0]["links"] == [
        {"label": "Repo", "url": "https://github.com/me/repo"},
        {"label": "Demo", "url": "https://demo.example.com"},
    ]
    assert context["sections"]["certifications"]["entries"][0]["links"] == [
        {"label": "Credential", "url": "https://verify.example.com/cert"}
    ]


def test_render_html_escapes_model_text_and_drops_unsafe_links() -> None:
    template_plan = _project_template_plan()
    resume_content = _project_resume_content(title="<script>alert('x')</script>")
    context = build_template_context(
        template_plan=template_plan,
        resume_content=resume_content,
        profile_items=[
            _profile_item(
                "project_1",
                ProfileItemKind.PROJECT,
                repo_url="javascript:alert(1)",
                url="https://safe.example.com/project",
            )
        ],
    )

    html = html_renderer.render_html(context)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "javascript:alert" not in html
    assert "https://safe.example.com/project" in html


def test_compile_resume_uses_weasyprint_without_latex_engine(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "artifacts_dir", tmp_path)
    monkeypatch.setattr(settings, "latex_engine", "definitely_missing_pdflatex")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("LaTeX subprocess should not be invoked")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    def fake_render_pdf(html, pdf_path):
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return 1

    monkeypatch.setattr(html_renderer, "render_pdf", fake_render_pdf)

    result = compile_resume(
        session_id=uuid4(),
        template_plan=_project_template_plan(),
        resume_content=_project_resume_content(),
        profile_items=[_profile_item("project_1", ProfileItemKind.PROJECT)],
    )

    assert result.success is True
    assert result.tex_path is not None
    assert result.html_path is not None
    assert result.pdf_path is not None
    assert result.log_path is not None
    assert result.page_count == 1
    assert "WeasyPrint" in result.compiler_output
    assert result.pdf_path.endswith("resume.pdf")
    assert result.html_path.endswith("resume.html")
    with open(result.pdf_path, "rb") as pdf_file:
        assert pdf_file.read().startswith(b"%PDF-")


def test_render_pdf_uses_weasyprint_when_system_libraries_are_available(tmp_path) -> None:
    try:
        import weasyprint  # noqa: F401
    except Exception as exc:
        pytest.skip(f"WeasyPrint native libraries are not available: {exc}")

    pdf_path = tmp_path / "resume.pdf"

    page_count = html_renderer.render_pdf("<html><body><p>Hello</p></body></html>", pdf_path)

    assert page_count == 1
    assert pdf_path.read_bytes().startswith(b"%PDF-")


def test_compile_resume_reports_weasyprint_failures(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "artifacts_dir", tmp_path)

    def fail_render(*args, **kwargs):
        raise RuntimeError("missing pango")

    monkeypatch.setattr(html_renderer, "render_pdf", fail_render)

    result = compile_resume(
        session_id=uuid4(),
        template_plan=_project_template_plan(),
        resume_content=_project_resume_content(),
        profile_items=[_profile_item("project_1", ProfileItemKind.PROJECT)],
    )

    assert result.success is False
    assert result.pdf_path is None
    assert result.tex_path is not None
    assert result.html_path is not None
    assert result.log_path is not None
    assert "missing pango" in result.compiler_output
    assert "fallback" not in result.compiler_output.lower()


def test_tailoring_records_weasyprint_compiler_and_html_metadata(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user_id = uuid4()
    job_id = uuid4()
    session_id = uuid4()
    source_item_id = "project_1"
    template_plan = _project_template_plan()
    resume_content = _project_resume_content()
    selection_plan = SelectionPlan(
        section_order=["projects"],
        selected_item_ids={"projects": [source_item_id]},
    )

    def fake_compile_resume(**kwargs):
        return CompileResult(
            success=True,
            tex_path="artifacts/session/resume.tex",
            html_path="artifacts/session/resume.html",
            pdf_path="artifacts/session/resume.pdf",
            log_path="artifacts/session/resume.log",
            page_count=1,
            compiler_output="Rendered PDF with WeasyPrint.",
        )

    monkeypatch.setattr(tailoring, "compile_resume", fake_compile_resume)

    with Session(engine) as session:
        spec_id = uuid4()
        session.add(
            JobSpecRecord(
                id=spec_id,
                job_id=job_id,
                version=1,
                schema_version="1.0",
                structured_json={},
                parsed_markdown="Backend Engineer",
                source_url="manual://test",
            )
        )
        session.add(
            UserProfileItem(
                user_id=user_id,
                source_item_id=source_item_id,
                kind=ProfileItemKind.PROJECT.value,
                payload=ProfileItemPayload(
                    title="Backend Tracker",
                    description="Built a FastAPI tracker.",
                    skills=["FastAPI"],
                ).model_dump(mode="json"),
            )
        )
        session.add(
            TailoringSession(
                id=session_id,
                user_id=user_id,
                job_id=job_id,
                job_spec_id=spec_id,
                status="content_draft",
                confirmed_selection_plan=selection_plan.model_dump(mode="json"),
                template_plan=template_plan.model_dump(mode="json"),
                resume_content=resume_content.model_dump(mode="json"),
            )
        )
        session.commit()

        _, result = tailoring.compile_tailored_resume(session, tailoring_session_id=session_id)
        compile_run = session.exec(select(CompileRun)).one()
        artifact = session.exec(select(ResumeArtifact)).one()

    assert result.html_path == "artifacts/session/resume.html"
    assert compile_run.compiler == HTML_RENDERER_NAME
    assert artifact.compile_metadata["html_path"] == "artifacts/session/resume.html"


def _project_template_plan() -> TemplatePlan:
    return TemplatePlan(
        section_order=["projects"],
        placeholders=[
            _placeholder(
                "projects_project_1_name",
                "project_1",
                ContentType.ENTRY_TITLE,
                "projects",
                "projects_project_1",
            ),
            _placeholder(
                "projects_project_1_tech_stack",
                "project_1",
                ContentType.TECH_STACK,
                "projects",
                "projects_project_1",
                required=False,
            ),
            _placeholder(
                "projects_project_1_dates",
                "project_1",
                ContentType.DATE_RANGE,
                "projects",
                "projects_project_1",
                required=False,
            ),
            _placeholder(
                "projects_project_1_bullet_1",
                "project_1",
                ContentType.RESUME_BULLET,
                "projects",
                "projects_project_1",
            ),
        ],
    )


def _project_resume_content(title: str = "Backend Tracker") -> ResumeContent:
    return ResumeContent(
        placeholder_values=[
            _value("projects_project_1_name", title, "project_1"),
            _value("projects_project_1_tech_stack", "Python, FastAPI", "project_1"),
            _value("projects_project_1_dates", "Jan 2026", "project_1"),
            _value("projects_project_1_bullet_1", "Built reliable APIs.", "project_1"),
        ]
    )


def _placeholder(
    placeholder_id: str,
    source_item_id: str,
    content_type: ContentType,
    section: str,
    entry_id: str | None = None,
    *,
    required: bool = True,
    field_label: str | None = None,
) -> TemplatePlaceholder:
    return TemplatePlaceholder(
        placeholder_id=placeholder_id,
        source_item_id=source_item_id,
        content_type=content_type,
        section=section,
        entry_id=entry_id,
        required=required,
        field_label=field_label,
    )


def _value(placeholder_id: str, text: str, source_item_id: str) -> PlaceholderValue:
    return PlaceholderValue(
        placeholder_id=placeholder_id,
        text=text,
        source_item_ids=[source_item_id],
    )


def _profile_item(
    source_item_id: str,
    kind: ProfileItemKind,
    **payload_updates,
) -> ProfileItemRead:
    return ProfileItemRead(
        id=f"{source_item_id}_id",
        user_id="user_1",
        kind=kind,
        source_item_id=source_item_id,
        payload=ProfileItemPayload(
            title=payload_updates.pop("title", source_item_id.replace("_", " ").title()),
            description=payload_updates.pop("description", "Profile evidence."),
            **payload_updates,
        ),
    )
