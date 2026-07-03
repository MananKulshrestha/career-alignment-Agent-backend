from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from app.core.config import settings
from app.schemas.profile import ProfileItemRead
from app.schemas.resume import CompileResult, ContentType, ResumeContent, TemplatePlan
from app.services.latex import assemble_latex

SUPPORTED_TEMPLATE_FAMILY = "jakes_resume"
TEMPLATE_NAME = "jakes_resume.html.j2"
CSS_NAME = "jakes_resume.css"
HTML_RENDERER_NAME = "weasyprint"


def build_template_context(
    *,
    template_plan: TemplatePlan,
    resume_content: ResumeContent,
    profile_items: list[ProfileItemRead],
) -> dict[str, Any]:
    if template_plan.template_family != SUPPORTED_TEMPLATE_FAMILY:
        raise ValueError(f"unsupported template_family: {template_plan.template_family}")

    content_by_placeholder = _content_by_placeholder(resume_content)
    profile_by_id = {item.source_item_id: item for item in profile_items}
    sections: dict[str, dict[str, Any]] = {}
    section_order: list[str] = []

    for section in template_plan.section_order:
        section_placeholders = _section_placeholders(template_plan, section)
        if not section_placeholders:
            continue

        section_context = _build_section_context(
            section=section,
            placeholders=section_placeholders,
            content_by_placeholder=content_by_placeholder,
            profile_by_id=profile_by_id,
        )
        if section_context:
            sections[section] = section_context
            section_order.append(section)

    return {
        "template_family": template_plan.template_family,
        "name": "Candidate Name",
        "contact": {
            "items": [
                {"label": "email@example.com", "url": "mailto:email@example.com"},
                {"label": "linkedin.com/in/...", "url": "https://linkedin.com/in/..."},
                {"label": "github.com/...", "url": "https://github.com/..."},
            ]
        },
        "section_order": section_order,
        "sections": sections,
    }


def render_html(context: dict[str, Any], html_path: Path | None = None) -> str:
    template = _jinja_environment().get_template(TEMPLATE_NAME)
    html = template.render(**context)
    if html_path is not None:
        html_path.write_text(html, encoding="utf-8")
    return html


def render_pdf(html: str, pdf_path: Path) -> int:
    from weasyprint import CSS, HTML

    css_text = _template_text(CSS_NAME)
    base_url = str(_template_dir())
    document = HTML(string=html, base_url=base_url).render(
        stylesheets=[CSS(string=css_text, base_url=base_url)]
    )
    document.write_pdf(pdf_path)
    return len(document.pages)


def compile_resume(
    *,
    session_id: UUID,
    template_plan: TemplatePlan,
    resume_content: ResumeContent,
    profile_items: list[ProfileItemRead],
) -> CompileResult:
    session_dir = settings.artifacts_dir / str(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    tex_path = session_dir / "resume.tex"
    html_path = session_dir / "resume.html"
    pdf_path = session_dir / "resume.pdf"
    log_path = session_dir / "resume.log"

    tex_path.write_text(
        assemble_latex(
            template_plan=template_plan,
            resume_content=resume_content,
            profile_items=profile_items,
        ),
        encoding="utf-8",
    )

    try:
        context = build_template_context(
            template_plan=template_plan,
            resume_content=resume_content,
            profile_items=profile_items,
        )
        html = render_html(context, html_path)
        page_count = render_pdf(html, pdf_path)
    except Exception as exc:  # noqa: BLE001 - preserve renderer diagnostics in artifacts.
        message = f"WeasyPrint render failed: {exc}"
        log_path.write_text(message + "\n", encoding="utf-8")
        return CompileResult(
            success=False,
            tex_path=str(tex_path),
            html_path=str(html_path) if html_path.exists() else None,
            log_path=str(log_path),
            compiler_output=message,
        )

    message = "Rendered PDF with WeasyPrint from the Jinja2 Jake resume template."
    log_path.write_text(message + "\n", encoding="utf-8")
    return CompileResult(
        success=True,
        tex_path=str(tex_path),
        html_path=str(html_path),
        pdf_path=str(pdf_path),
        log_path=str(log_path),
        page_count=page_count,
        compiler_output=message,
    )


def _build_section_context(
    *,
    section: str,
    placeholders: list,
    content_by_placeholder: dict[str, str],
    profile_by_id: dict[str, ProfileItemRead],
) -> dict[str, Any] | None:
    if section == "technical_skills":
        skills = []
        for placeholder in placeholders:
            text = content_by_placeholder.get(placeholder.placeholder_id, "")
            if text:
                skills.append({"label": placeholder.field_label or "Skills", "items": text})
        if not skills:
            return None
        return {"label": _section_label(section), "skills": skills}

    if section == "summary":
        paragraphs = [
            content_by_placeholder.get(placeholder.placeholder_id, "")
            for placeholder in placeholders
            if content_by_placeholder.get(placeholder.placeholder_id, "")
        ]
        if not paragraphs:
            return None
        return {"label": _section_label(section), "paragraphs": paragraphs}

    entries = []
    for entry_placeholders in _group_by_entry(placeholders).values():
        entry = _build_entry_context(
            section=section,
            placeholders=entry_placeholders,
            content_by_placeholder=content_by_placeholder,
            profile_by_id=profile_by_id,
        )
        if _entry_has_content(entry):
            entries.append(entry)
    if not entries:
        return None
    return {"label": _section_label(section), "entries": entries}


def _build_entry_context(
    *,
    section: str,
    placeholders: list,
    content_by_placeholder: dict[str, str],
    profile_by_id: dict[str, ProfileItemRead],
) -> dict[str, Any]:
    source_id = placeholders[0].source_item_id if placeholders else ""
    return {
        "title": _first_content(placeholders, content_by_placeholder, ContentType.ENTRY_TITLE),
        "organization": _first_content(
            placeholders, content_by_placeholder, ContentType.ENTRY_ORGANIZATION
        ),
        "location": _first_content(placeholders, content_by_placeholder, ContentType.LOCATION),
        "dates": _first_content(placeholders, content_by_placeholder, ContentType.DATE_RANGE),
        "tech_stack": _first_content(placeholders, content_by_placeholder, ContentType.TECH_STACK),
        "links": _profile_links(source_id, profile_by_id) if section != "experience" else [],
        "bullets": _bullet_contents(placeholders, content_by_placeholder),
    }


def _profile_links(
    source_item_id: str, profile_by_id: dict[str, ProfileItemRead]
) -> list[dict[str, str]]:
    item = profile_by_id.get(source_item_id)
    if not item:
        return []
    payload = item.payload
    candidates = [
        ("Repo", getattr(payload, "repo_url", None) or ""),
        ("Demo", getattr(payload, "demo_url", None) or ""),
        ("Credential", getattr(payload, "credential_url", None) or ""),
    ]
    links = [
        {"label": label, "url": sanitized_url}
        for label, url in candidates
        if (sanitized_url := _safe_url(url))
    ]
    if links:
        return links
    fallback_url = _safe_url(getattr(payload, "url", None) or "")
    return [{"label": "Link", "url": fallback_url}] if fallback_url else []


def _safe_url(value: str) -> str | None:
    url = value.strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return url
    if parsed.scheme.lower() == "mailto" and parsed.path:
        return url
    return None


def _content_by_placeholder(resume_content: ResumeContent) -> dict[str, str]:
    return {value.placeholder_id: value.text for value in resume_content.placeholder_values}


def _section_placeholders(template_plan: TemplatePlan, section: str):
    return [
        placeholder
        for placeholder in template_plan.placeholders
        if placeholder.section == section or placeholder.placeholder_id.startswith(f"{section}_")
    ]


def _group_by_entry(placeholders):
    grouped: dict[str, list] = {}
    for placeholder in placeholders:
        entry_id = placeholder.entry_id or placeholder.source_item_id
        grouped.setdefault(entry_id, []).append(placeholder)
    return grouped


def _first_content(
    placeholders, content_by_placeholder: dict[str, str], content_type: ContentType
) -> str:
    for placeholder in placeholders:
        if placeholder.content_type == content_type:
            return content_by_placeholder.get(placeholder.placeholder_id, "")
    return ""


def _bullet_contents(placeholders, content_by_placeholder: dict[str, str]) -> list[str]:
    return [
        content_by_placeholder.get(placeholder.placeholder_id, "")
        for placeholder in placeholders
        if placeholder.content_type == ContentType.RESUME_BULLET
        and content_by_placeholder.get(placeholder.placeholder_id, "")
    ]


def _entry_has_content(entry: dict[str, Any]) -> bool:
    return any(
        entry.get(key)
        for key in ("title", "organization", "location", "dates", "tech_stack", "links", "bullets")
    )


def _section_label(section: str) -> str:
    return section.replace("_", " ").title()


def _jinja_environment() -> Environment:
    return Environment(
        loader=PackageLoader("app", "templates"),
        autoescape=select_autoescape(
            enabled_extensions=("html", "html.j2"),
            default_for_string=True,
            default=True,
        ),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _template_text(name: str) -> str:
    return resources.files("app").joinpath("templates", name).read_text(encoding="utf-8")


def _template_dir() -> Any:
    return resources.files("app").joinpath("templates")
