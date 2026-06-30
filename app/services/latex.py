from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.schemas.profile import ProfileItemRead
from app.schemas.resume import CompileResult, ResumeContent, TemplatePlan

LATEX_SPECIAL_CHARS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_latex(value: str) -> str:
    return "".join(LATEX_SPECIAL_CHARS.get(char, char) for char in value)


def assemble_latex(
    *,
    template_plan: TemplatePlan,
    resume_content: ResumeContent,
    profile_items: list[ProfileItemRead],
) -> str:
    profile_by_id = {item.source_item_id: item for item in profile_items}
    content_by_placeholder = {
        value.placeholder_id: escape_latex(value.text)
        for value in resume_content.placeholder_values
    }
    lines = [
        r"\documentclass[10pt,letterpaper]{article}",
        r"\usepackage[margin=0.55in]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{enumitem}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\setlength{\parindent}{0pt}",
        r"\setlist[itemize]{leftmargin=*, itemsep=2pt, topsep=2pt}",
        r"\begin{document}",
        r"\begin{center}",
        r"{\LARGE Candidate Name}\\",
        r"\href{mailto:email@example.com}{email@example.com} \quad LinkedIn \quad GitHub",
        r"\end{center}",
    ]

    for section in template_plan.section_order:
        section_placeholders = [
            placeholder
            for placeholder in template_plan.placeholders
            if placeholder.placeholder_id.startswith(f"{section}_")
        ]
        if not section_placeholders:
            continue
        lines.extend(
            [
                r"\vspace{4pt}",
                rf"\textbf{{{escape_latex(_section_label(section))}}}",
                r"\begin{itemize}",
            ]
        )
        for placeholder in section_placeholders:
            item = profile_by_id.get(placeholder.source_item_id)
            prefix = ""
            if item and item.payload.title:
                prefix = rf"\textbf{{{escape_latex(item.payload.title)}}}: "
            text = content_by_placeholder.get(placeholder.placeholder_id, "")
            if text:
                lines.append(rf"\item {prefix}{text}")
        lines.append(r"\end{itemize}")

    lines.append(r"\end{document}")
    return "\n".join(lines)


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

    command = [
        settings.latex_engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        tex_path.name,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=session_dir,
            capture_output=True,
            text=True,
            timeout=settings.latex_compile_timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        page_count = render_fallback_pdf(
            pdf_path=pdf_path,
            log_path=log_path,
            template_plan=template_plan,
            resume_content=resume_content,
            profile_items=profile_items,
        )
        return CompileResult(
            success=True,
            tex_path=str(tex_path),
            pdf_path=str(pdf_path),
            log_path=str(log_path),
            page_count=page_count,
            compiler_output=(
                f"LaTeX engine not found: {settings.latex_engine}. "
                "Rendered ATS-readable PDF with the built-in fallback renderer."
            ),
        )
    except subprocess.TimeoutExpired as exc:
        return CompileResult(
            success=False,
            tex_path=str(tex_path),
            log_path=str(log_path),
            compiler_output=f"LaTeX compile timed out: {exc}",
        )

    compiler_output = "\n".join([completed.stdout, completed.stderr]).strip()
    if log_path.exists():
        compiler_output = (
            f"{compiler_output}\n\n{log_path.read_text(encoding='utf-8', errors='ignore')}"
        )
    return CompileResult(
        success=completed.returncode == 0 and pdf_path.exists(),
        tex_path=str(tex_path),
        pdf_path=str(pdf_path) if pdf_path.exists() else None,
        log_path=str(log_path) if log_path.exists() else None,
        page_count=None,
        compiler_output=compiler_output[-6000:],
    )


def render_fallback_pdf(
    *,
    pdf_path: Path,
    log_path: Path,
    template_plan: TemplatePlan,
    resume_content: ResumeContent,
    profile_items: list[ProfileItemRead],
) -> int:
    """Render a plain PDF when a TeX distribution is not installed."""

    line_specs = _fallback_line_specs(
        template_plan=template_plan,
        resume_content=resume_content,
        profile_items=profile_items,
    )
    pages = _paginate_pdf_lines(line_specs)
    _write_simple_pdf(pdf_path, pages)
    log_path.write_text(
        "LaTeX engine was unavailable; generated a plain ATS-readable PDF fallback.\n",
        encoding="utf-8",
    )
    return len(pages)


def _fallback_line_specs(
    *,
    template_plan: TemplatePlan,
    resume_content: ResumeContent,
    profile_items: list[ProfileItemRead],
) -> list[tuple[str, float, int]]:
    profile_by_id = {item.source_item_id: item for item in profile_items}
    content_by_placeholder = {
        value.placeholder_id: value.text for value in resume_content.placeholder_values
    }
    lines: list[tuple[str, float, int]] = [
        ("Candidate Name", 54, 16),
        ("email@example.com | LinkedIn | GitHub", 54, 10),
        ("", 54, 8),
    ]

    for section in template_plan.section_order:
        section_placeholders = [
            placeholder
            for placeholder in template_plan.placeholders
            if placeholder.placeholder_id.startswith(f"{section}_")
        ]
        if not section_placeholders:
            continue
        lines.append((_section_label(section).upper(), 54, 12))
        for placeholder in section_placeholders:
            text = content_by_placeholder.get(placeholder.placeholder_id, "")
            if not text:
                continue
            item = profile_by_id.get(placeholder.source_item_id)
            prefix = f"{item.payload.title}: " if item and item.payload.title else ""
            lines.extend(_wrap_pdf_bullet(f"{prefix}{text}"))
        lines.append(("", 54, 8))
    return lines


def _wrap_pdf_bullet(text: str) -> list[tuple[str, float, int]]:
    wrapped = textwrap.wrap(
        " ".join(text.split()),
        width=92,
        break_long_words=True,
        replace_whitespace=True,
    ) or [text]
    return [
        (f"- {line}" if index == 0 else f"  {line}", 60, 10) for index, line in enumerate(wrapped)
    ]


def _paginate_pdf_lines(
    line_specs: list[tuple[str, float, int]],
) -> list[list[tuple[str, float, float, int]]]:
    pages: list[list[tuple[str, float, float, int]]] = []
    current_page: list[tuple[str, float, float, int]] = []
    y_position = 742.0

    for text, x_position, font_size in line_specs:
        if not text:
            y_position -= 8
            continue
        if y_position < 54:
            pages.append(current_page)
            current_page = []
            y_position = 742.0
        current_page.append((text, x_position, y_position, font_size))
        y_position -= font_size + 4

    if current_page:
        pages.append(current_page)
    return pages or [[("Candidate Name", 54, 742, 16)]]


def _write_simple_pdf(pdf_path: Path, pages: list[list[tuple[str, float, float, int]]]) -> None:
    objects: list[bytes | None] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_refs: list[str] = []
    for page in pages:
        page_object_number = len(objects) + 1
        content_object_number = page_object_number + 1
        page_refs.append(f"{page_object_number} 0 R")
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_object_number} 0 R >>"
            ).encode("ascii")
        )
        stream = "\n".join(
            f"BT /F1 {font_size} Tf {x_position:.1f} {y_position:.1f} Td "
            f"({_escape_pdf_text(text)}) Tj ET"
            for text, x_position, y_position, font_size in page
        ).encode("latin-1", errors="replace")
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    objects[1] = (
        f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>"
    ).encode("ascii")
    _write_pdf_objects(pdf_path, [item for item in objects if item is not None])


def _write_pdf_objects(pdf_path: Path, objects: list[bytes]) -> None:
    offsets = [0]
    with pdf_path.open("wb") as pdf_file:
        pdf_file.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        for index, payload in enumerate(objects, start=1):
            offsets.append(pdf_file.tell())
            pdf_file.write(f"{index} 0 obj\n".encode("ascii"))
            pdf_file.write(payload)
            pdf_file.write(b"\nendobj\n")
        xref_offset = pdf_file.tell()
        pdf_file.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        pdf_file.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf_file.write(f"{offset:010d} 00000 n \n".encode("ascii"))
        pdf_file.write(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("ascii")
        )


def _escape_pdf_text(value: str) -> str:
    ascii_text = value.encode("latin-1", errors="replace").decode("latin-1")
    return ascii_text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _section_label(section: str) -> str:
    return section.replace("_", " ").title()
