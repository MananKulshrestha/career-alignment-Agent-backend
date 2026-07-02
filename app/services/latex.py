from __future__ import annotations

import subprocess
import textwrap
from dataclasses import dataclass
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

PDF_PAGE_WIDTH = 612.0
PDF_PAGE_HEIGHT = 792.0
PDF_MARGIN_X = 45.0
PDF_TOP_Y = 744.0
PDF_BOTTOM_Y = 54.0
PDF_TEXT_RIGHT = PDF_PAGE_WIDTH - PDF_MARGIN_X


@dataclass(frozen=True)
class _PdfText:
    text: str
    x_position: float
    y_position: float
    font_size: float
    font_name: str = "F1"


@dataclass(frozen=True)
class _PdfRule:
    x_start: float
    y_position: float
    x_end: float
    line_width: float = 0.35


@dataclass(frozen=True)
class _PdfDot:
    x_position: float
    y_position: float
    radius: float = 1.35


_PdfDrawOp = _PdfText | _PdfRule | _PdfDot


@dataclass(frozen=True)
class _PdfLink:
    url: str
    x_start: float
    y_bottom: float
    x_end: float
    y_top: float


def escape_latex(value: str) -> str:
    return "".join(LATEX_SPECIAL_CHARS.get(char, char) for char in value)


def _get_entry_url_latex(source_item_id: str, profile_by_id: dict[str, ProfileItemRead]) -> str:
    """Build LaTeX \\href links for a profile item's URLs."""
    item = profile_by_id.get(source_item_id)
    if not item:
        return ""
    payload = item.payload
    parts: list[str] = []
    repo = getattr(payload, "repo_url", None) or ""
    demo = getattr(payload, "demo_url", None) or ""
    cred = getattr(payload, "credential_url", None) or ""
    link = getattr(payload, "url", None) or ""
    if repo.strip():
        parts.append(rf"\href{{{repo.strip()}}}{{Repo}}")
    if demo.strip():
        parts.append(rf"\href{{{demo.strip()}}}{{Demo}}")
    if cred.strip():
        parts.append(rf"\href{{{cred.strip()}}}{{Credential}}")
    if not parts and link.strip():
        parts.append(rf"\href{{{link.strip()}}}{{Link}}")
    return r" \textbar\ ".join(parts)


def _get_entry_urls(source_item_id: str, profile_by_id: dict[str, ProfileItemRead]) -> list[tuple[str, str]]:
    """Return (label, url) pairs for a profile item's URLs."""
    item = profile_by_id.get(source_item_id)
    if not item:
        return []
    payload = item.payload
    parts: list[tuple[str, str]] = []
    repo = getattr(payload, "repo_url", None) or ""
    demo = getattr(payload, "demo_url", None) or ""
    cred = getattr(payload, "credential_url", None) or ""
    link = getattr(payload, "url", None) or ""
    if repo.strip():
        parts.append(("Repo", repo.strip()))
    if demo.strip():
        parts.append(("Demo", demo.strip()))
    if cred.strip():
        parts.append(("Credential", cred.strip()))
    if not parts and link.strip():
        parts.append(("Link", link.strip()))
    return parts


def assemble_latex(
    *,
    template_plan: TemplatePlan,
    resume_content: ResumeContent,
    profile_items: list[ProfileItemRead],
) -> str:
    content_by_placeholder = _content_by_placeholder(resume_content, escape=True)
    profile_by_id = {item.source_item_id: item for item in profile_items}
    lines = _jake_preamble()
    lines.extend(_jake_heading())

    for section in template_plan.section_order:
        section_placeholders = _section_placeholders(template_plan, section)
        if not section_placeholders:
            continue
        if section == "technical_skills":
            lines.extend(_render_skills_section(section_placeholders, content_by_placeholder))
        elif section == "summary":
            lines.extend(_render_summary_section(section_placeholders, content_by_placeholder))
        elif section == "education" or section == "experience":
            lines.extend(
                _render_subheading_section(section, section_placeholders, content_by_placeholder)
            )
        elif section == "projects":
            lines.extend(_render_projects_section(section_placeholders, content_by_placeholder, profile_by_id))
        elif section in {"achievements", "certifications"}:
            lines.extend(
                _render_project_like_section(section, section_placeholders, content_by_placeholder, profile_by_id)
            )

    lines.append(r"\end{document}")
    return "\n".join(lines)


def _jake_preamble() -> list[str]:
    return [
        r"\documentclass[letterpaper,11pt]{article}",
        "",
        r"\usepackage{latexsym}",
        r"\usepackage[empty]{fullpage}",
        r"\usepackage{titlesec}",
        r"\usepackage{marvosym}",
        r"\usepackage[usenames,dvipsnames]{color}",
        r"\usepackage{verbatim}",
        r"\usepackage{enumitem}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\usepackage{fancyhdr}",
        r"\usepackage[english]{babel}",
        r"\usepackage{tabularx}",
        r"\input{glyphtounicode}",
        "",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        r"\fancyfoot{}",
        r"\renewcommand{\headrulewidth}{0pt}",
        r"\renewcommand{\footrulewidth}{0pt}",
        "",
        r"\addtolength{\oddsidemargin}{-0.5in}",
        r"\addtolength{\evensidemargin}{-0.5in}",
        r"\addtolength{\textwidth}{1in}",
        r"\addtolength{\topmargin}{-.5in}",
        r"\addtolength{\textheight}{1.0in}",
        "",
        r"\urlstyle{same}",
        r"\raggedbottom",
        r"\raggedright",
        r"\setlength{\tabcolsep}{0in}",
        "",
        r"\titleformat{\section}{",
        r"  \vspace{-4pt}\scshape\raggedright\large",
        r"}{}{0em}{}[\color{black}\titlerule \vspace{-5pt}]",
        "",
        r"\pdfgentounicode=1",
        "",
        r"\newcommand{\resumeItem}[1]{",
        r"  \item\small{",
        r"    {#1 \vspace{-2pt}}",
        r"  }",
        r"}",
        "",
        r"\newcommand{\resumeSubheading}[4]{",
        r"  \vspace{-2pt}\item",
        r"    \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}",
        r"      \textbf{#1} & #2 \\",
        r"      \textit{\small#3} & \textit{\small #4} \\",
        r"    \end{tabular*}\vspace{-7pt}",
        r"}",
        "",
        r"\newcommand{\resumeProjectHeading}[2]{",
        r"    \item",
        r"    \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}",
        r"      \small#1 & #2 \\",
        r"    \end{tabular*}\vspace{-7pt}",
        r"}",
        "",
        r"\newcommand{\resumeSubItem}[1]{\resumeItem{#1}\vspace{-4pt}}",
        r"\renewcommand\labelitemii{$\vcenter{\hbox{\tiny$\bullet$}}$}",
        r"\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}",
        r"\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}",
        r"\newcommand{\resumeItemListStart}{\begin{itemize}}",
        r"\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}",
        "",
        r"\begin{document}",
    ]


def _jake_heading() -> list[str]:
    return [
        r"\begin{center}",
        r"    \textbf{\Huge \scshape Candidate Name} \\ \vspace{1pt}",
        r"    \small \href{mailto:email@example.com}{\underline{email@example.com}} $|$",
        r"    \href{https://linkedin.com/in/...}{\underline{linkedin.com/in/...}} $|$",
        r"    \href{https://github.com/...}{\underline{github.com/...}}",
        r"\end{center}",
        "",
    ]


def _content_by_placeholder(resume_content: ResumeContent, *, escape: bool) -> dict[str, str]:
    if escape:
        return {
            value.placeholder_id: escape_latex(value.text)
            for value in resume_content.placeholder_values
        }
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


def _render_summary_section(placeholders, content_by_placeholder: dict[str, str]) -> list[str]:
    summaries = [
        content_by_placeholder.get(placeholder.placeholder_id, "")
        for placeholder in placeholders
        if content_by_placeholder.get(placeholder.placeholder_id, "")
    ]
    if not summaries:
        return []
    return [
        r"\section{Summary}",
        r"\small{" + " ".join(summaries) + r"}",
        "",
    ]


def _render_subheading_section(
    section: str, placeholders, content_by_placeholder: dict[str, str]
) -> list[str]:
    lines = [
        rf"\section{{{escape_latex(_section_label(section))}}}",
        r"  \resumeSubHeadingListStart",
    ]
    for entry_placeholders in _group_by_entry(placeholders).values():
        title = _first_content(entry_placeholders, content_by_placeholder, "entry_title")
        organization = _first_content(
            entry_placeholders, content_by_placeholder, "entry_organization"
        )
        location = _first_content(entry_placeholders, content_by_placeholder, "location")
        dates = _first_content(entry_placeholders, content_by_placeholder, "date_range")
        if section == "education":
            first_left = organization
            first_right = location
            second_left = title
            second_right = dates
        else:
            first_left = title
            first_right = dates
            second_left = organization
            second_right = location

        lines.extend(
            [
                r"    \resumeSubheading",
                rf"      {{{first_left}}}{{{first_right}}}",
                rf"      {{{second_left}}}{{{second_right}}}",
            ]
        )
        bullets = _bullet_contents(entry_placeholders, content_by_placeholder)
        if bullets:
            lines.append(r"      \resumeItemListStart")
            lines.extend(rf"        \resumeItem{{{bullet}}}" for bullet in bullets)
            lines.append(r"      \resumeItemListEnd")
    lines.extend([r"  \resumeSubHeadingListEnd", ""])
    return lines


def _render_projects_section(
    placeholders, content_by_placeholder: dict[str, str],
    profile_by_id: dict[str, ProfileItemRead],
) -> list[str]:
    lines = [r"\section{Projects}", r"    \resumeSubHeadingListStart"]
    for entry_placeholders in _group_by_entry(placeholders).values():
        title = _first_content(entry_placeholders, content_by_placeholder, "entry_title")
        tech_stack = _first_content(entry_placeholders, content_by_placeholder, "tech_stack")
        dates = _first_content(entry_placeholders, content_by_placeholder, "date_range")
        heading = rf"\textbf{{{title}}}"
        if tech_stack:
            heading = rf"{heading} \textbar\ \emph{{{tech_stack}}}"
        source_id = entry_placeholders[0].source_item_id if entry_placeholders else ""
        url_links = _get_entry_url_latex(source_id, profile_by_id)
        right_content = dates
        if url_links:
            right_content = f"{right_content} {url_links}".strip()
        lines.extend(
            [
                r"      \resumeProjectHeading",
                rf"          {{{heading}}}{{{right_content}}}",
            ]
        )
        bullets = _bullet_contents(entry_placeholders, content_by_placeholder)
        if bullets:
            lines.append(r"          \resumeItemListStart")
            lines.extend(rf"            \resumeItem{{{bullet}}}" for bullet in bullets)
            lines.append(r"          \resumeItemListEnd")
    lines.extend([r"    \resumeSubHeadingListEnd", ""])
    return lines


def _render_project_like_section(
    section: str, placeholders, content_by_placeholder: dict[str, str],
    profile_by_id: dict[str, ProfileItemRead],
) -> list[str]:
    lines = [
        rf"\section{{{escape_latex(_section_label(section))}}}",
        r"    \resumeSubHeadingListStart",
    ]
    for entry_placeholders in _group_by_entry(placeholders).values():
        title = _first_content(entry_placeholders, content_by_placeholder, "entry_title")
        organization = _first_content(
            entry_placeholders, content_by_placeholder, "entry_organization"
        )
        dates = _first_content(entry_placeholders, content_by_placeholder, "date_range")
        heading = rf"\textbf{{{title}}}"
        if organization:
            heading = rf"{heading} \textbar\ \emph{{{organization}}}"
        source_id = entry_placeholders[0].source_item_id if entry_placeholders else ""
        url_links = _get_entry_url_latex(source_id, profile_by_id)
        right_content = dates
        if url_links:
            right_content = f"{right_content} {url_links}".strip()
        lines.extend(
            [
                r"      \resumeProjectHeading",
                rf"          {{{heading}}}{{{right_content}}}",
            ]
        )
        bullets = _bullet_contents(entry_placeholders, content_by_placeholder)
        if bullets:
            lines.append(r"          \resumeItemListStart")
            lines.extend(rf"            \resumeItem{{{bullet}}}" for bullet in bullets)
            lines.append(r"          \resumeItemListEnd")
    lines.extend([r"    \resumeSubHeadingListEnd", ""])
    return lines


def _render_skills_section(placeholders, content_by_placeholder: dict[str, str]) -> list[str]:
    skill_lines: list[str] = []
    for placeholder in placeholders:
        text = content_by_placeholder.get(placeholder.placeholder_id, "")
        if not text:
            continue
        label = escape_latex(placeholder.field_label or "Skills")
        skill_lines.append(rf"     \textbf{{{label}}}{{: {text}}}")
    if not skill_lines:
        return []
    joined_skill_lines = (r" \\" + "\n").join(skill_lines)
    return [
        r"\section{Technical Skills}",
        r" \begin{itemize}[leftmargin=0.15in, label={}]",
        r"    \small{\item{",
        joined_skill_lines,
        r"    }}",
        r" \end{itemize}",
        "",
    ]


def _first_content(placeholders, content_by_placeholder: dict[str, str], content_type: str) -> str:
    for placeholder in placeholders:
        if placeholder.content_type == content_type:
            return content_by_placeholder.get(placeholder.placeholder_id, "")
    return ""


def _bullet_contents(placeholders, content_by_placeholder: dict[str, str]) -> list[str]:
    return [
        content_by_placeholder.get(placeholder.placeholder_id, "")
        for placeholder in placeholders
        if placeholder.content_type == "resume_bullet"
        and content_by_placeholder.get(placeholder.placeholder_id, "")
    ]


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
    """Render a Jake-style PDF when a TeX distribution is not installed."""

    pages, page_links = _jake_fallback_pages(
        template_plan=template_plan,
        resume_content=resume_content,
        profile_items=profile_items,
    )
    _write_jake_fallback_pdf(pdf_path, pages, page_links)
    log_path.write_text(
        "LaTeX engine was unavailable; generated a Jake-style ATS-readable PDF fallback.\n",
        encoding="utf-8",
    )
    return len(pages)


class _JakeFallbackPdfBuilder:
    def __init__(self) -> None:
        self.pages: list[list[_PdfDrawOp]] = [[]]
        self.page_links: list[list[_PdfLink]] = [[]]
        self.y_position = PDF_TOP_Y

    def center_text(
        self, text: str, *, font_size: float, font_name: str = "F1", leading: float
    ) -> None:
        x_position = (PDF_PAGE_WIDTH - _pdf_text_width(text, font_size, font_name)) / 2
        self.text(
            text,
            x_position=max(PDF_MARGIN_X, x_position),
            font_size=font_size,
            font_name=font_name,
            leading=leading,
        )

    def text(
        self,
        text: str,
        *,
        x_position: float = PDF_MARGIN_X,
        font_size: float = 10,
        font_name: str = "F1",
        leading: float = 12,
    ) -> None:
        if not text:
            return
        self.ensure_space(leading)
        self.pages[-1].append(
            _PdfText(
                text=text,
                x_position=x_position,
                y_position=self.y_position,
                font_size=font_size,
                font_name=font_name,
            )
        )
        self.y_position -= leading

    def paired_text(
        self,
        left_text: str,
        right_text: str,
        *,
        left_font: str = "F1",
        right_font: str = "F1",
        font_size: float = 10,
        leading: float = 11,
    ) -> None:
        if not left_text and not right_text:
            return
        self.ensure_space(leading)
        if left_text:
            self.pages[-1].append(
                _PdfText(left_text, PDF_MARGIN_X + 15, self.y_position, font_size, left_font)
            )
        if right_text:
            self.pages[-1].append(
                _PdfText(
                    right_text,
                    PDF_TEXT_RIGHT - _pdf_text_width(right_text, font_size, right_font),
                    self.y_position,
                    font_size,
                    right_font,
                )
            )
        self.y_position -= leading

    def text_runs(
        self,
        runs: list[tuple[str, str]],
        *,
        right_text: str = "",
        font_size: float = 10,
        leading: float = 12,
    ) -> None:
        if not any(text for text, _ in runs) and not right_text:
            return
        self.ensure_space(leading)
        x_position = PDF_MARGIN_X + 15
        right_edge = PDF_TEXT_RIGHT
        if right_text:
            right_x = PDF_TEXT_RIGHT - _pdf_text_width(right_text, font_size, "F1")
            self.pages[-1].append(_PdfText(right_text, right_x, self.y_position, font_size, "F1"))
            right_edge = right_x - 12
        for text, font_name in runs:
            if not text:
                continue
            available_width = max(24.0, right_edge - x_position)
            clipped_text = _clip_pdf_text(text, available_width, font_size, font_name)
            self.pages[-1].append(
                _PdfText(clipped_text, x_position, self.y_position, font_size, font_name)
            )
            x_position += _pdf_text_width(clipped_text, font_size, font_name)
        self.y_position -= leading

    def section(self, label: str) -> None:
        self.ensure_space(24)
        self.pages[-1].append(_PdfText(label, PDF_MARGIN_X, self.y_position, 12, "F1"))
        self.pages[-1].append(_PdfRule(PDF_MARGIN_X, self.y_position - 3, PDF_TEXT_RIGHT))
        self.y_position -= 16

    def paragraph(self, text: str) -> None:
        for index, line in enumerate(_wrap_pdf_text(text, width_points=500, font_size=9.5)):
            self.text(
                line,
                x_position=PDF_MARGIN_X + 15,
                font_size=9.5,
                font_name="F1",
                leading=11 if index else 12,
            )

    def bullet(self, text: str) -> None:
        wrapped = _wrap_pdf_text(text, width_points=470, font_size=9.5)
        for index, line in enumerate(wrapped):
            self.ensure_space(11)
            if index == 0:
                self.pages[-1].append(_PdfDot(PDF_MARGIN_X + 33, self.y_position + 3.2))
            self.pages[-1].append(_PdfText(line, PDF_MARGIN_X + 43, self.y_position, 9.5, "F1"))
            self.y_position -= 11

    def small_gap(self, amount: float = 3) -> None:
        self.y_position -= amount

    def ensure_space(self, required_height: float) -> None:
        if self.y_position - required_height >= PDF_BOTTOM_Y:
            return
        self.pages.append([])
        self.page_links.append([])
        self.y_position = PDF_TOP_Y

    def draw_url_links(
        self, links: list[tuple[str, str]], *, font_size: float = 9.0
    ) -> None:
        """Draw right-aligned clickable URL labels on the current heading line."""
        if not links:
            return
        sep = " \u00b7 "
        # Calculate total width
        total_w = sum(_pdf_text_width(label, font_size, "F1") for label, _ in links)
        if len(links) > 1:
            total_w += _pdf_text_width(sep, font_size, "F1") * (len(links) - 1)
        # Draw on the line that was just rendered (y was already decremented)
        y = self.y_position + 12
        x = PDF_TEXT_RIGHT - total_w
        for i, (label, url) in enumerate(links):
            w = _pdf_text_width(label, font_size, "F1")
            self.pages[-1].append(_PdfText(label, x, y, font_size, "F1"))
            self.page_links[-1].append(
                _PdfLink(url=url, x_start=x - 1, y_bottom=y - 2, x_end=x + w + 1, y_top=y + font_size + 2)
            )
            x += w
            if i < len(links) - 1:
                sw = _pdf_text_width(sep, font_size, "F1")
                self.pages[-1].append(_PdfText(sep, x, y, font_size, "F1"))
                x += sw


def _jake_fallback_pages(
    *,
    template_plan: TemplatePlan,
    resume_content: ResumeContent,
    profile_items: list[ProfileItemRead],
) -> list[list[_PdfDrawOp]]:
    content_by_placeholder = _content_by_placeholder(resume_content, escape=False)
    profile_by_id = {item.source_item_id: item for item in profile_items}
    builder = _JakeFallbackPdfBuilder()
    builder.center_text("Candidate Name", font_size=24, font_name="F2", leading=18)
    builder.center_text(
        "email@example.com | linkedin.com/in/... | github.com/...",
        font_size=9,
        font_name="F1",
        leading=22,
    )

    for section in template_plan.section_order:
        section_placeholders = _section_placeholders(template_plan, section)
        if not section_placeholders:
            continue
        builder.section(_section_label(section))

        if section == "technical_skills":
            for placeholder in section_placeholders:
                text = content_by_placeholder.get(placeholder.placeholder_id, "")
                if text:
                    label = placeholder.field_label or "Skills"
                    builder.text_runs(
                        [(f"{label}: ", "F2"), (f" {text}", "F1")],
                        font_size=9.5,
                        leading=11,
                    )
            builder.small_gap(4)
            continue

        if section == "summary":
            for placeholder in section_placeholders:
                text = content_by_placeholder.get(placeholder.placeholder_id, "")
                if text:
                    builder.paragraph(text)
            builder.small_gap(4)
            continue

        for entry_placeholders in _group_by_entry(section_placeholders).values():
            title = _first_content(entry_placeholders, content_by_placeholder, "entry_title")
            organization = _first_content(
                entry_placeholders, content_by_placeholder, "entry_organization"
            )
            location = _first_content(entry_placeholders, content_by_placeholder, "location")
            dates = _first_content(entry_placeholders, content_by_placeholder, "date_range")
            tech_stack = _first_content(entry_placeholders, content_by_placeholder, "tech_stack")

            if section == "education":
                builder.paired_text(
                    organization,
                    location,
                    left_font="F2",
                    right_font="F1",
                    font_size=10,
                )
                builder.paired_text(
                    title,
                    dates,
                    left_font="F3",
                    right_font="F3",
                    font_size=9.5,
                )
            elif section == "experience":
                builder.paired_text(title, dates, left_font="F2", font_size=10)
                builder.paired_text(
                    organization,
                    location,
                    left_font="F3",
                    right_font="F3",
                    font_size=9.5,
                )
            elif section == "projects":
                runs = [(title, "F2")]
                if tech_stack:
                    runs.extend([(" | ", "F1"), (tech_stack, "F3")])
                builder.text_runs(runs, right_text=dates, font_size=10, leading=12)
                source_id = entry_placeholders[0].source_item_id if entry_placeholders else ""
                builder.draw_url_links(_get_entry_urls(source_id, profile_by_id))
            else:
                runs = [(title, "F2")]
                if organization:
                    runs.extend([(" | ", "F1"), (organization, "F3")])
                builder.text_runs(runs, right_text=dates, font_size=10, leading=12)
                source_id = entry_placeholders[0].source_item_id if entry_placeholders else ""
                builder.draw_url_links(_get_entry_urls(source_id, profile_by_id))

            for text in _bullet_contents(entry_placeholders, content_by_placeholder):
                if not text:
                    continue
                builder.bullet(text)
            builder.small_gap(3)
        builder.small_gap(4)
    if any(builder.pages):
        return builder.pages, builder.page_links
    return [[_PdfText("Candidate Name", 244, 744, 24, "F2")]], [[]]


def _write_jake_fallback_pdf(
    pdf_path: Path,
    pages: list[list[_PdfDrawOp]],
    page_links: list[list[_PdfLink]] | None = None,
) -> None:
    objects: list[bytes | None] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Italic /Encoding /WinAnsiEncoding >>",
    ]
    page_refs: list[str] = []
    for page_idx, page in enumerate(pages):
        links = page_links[page_idx] if page_links and page_idx < len(page_links) else []
        page_object_number = len(objects) + 1
        content_object_number = page_object_number + 1
        annot_start = content_object_number + 1
        annot_refs = [f"{annot_start + i} 0 R" for i in range(len(links))]
        page_refs.append(f"{page_object_number} 0 R")
        annots_str = f" /Annots [{' '.join(annot_refs)}]" if annot_refs else ""
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PDF_PAGE_WIDTH:.0f} "
                f"{PDF_PAGE_HEIGHT:.0f}] /Resources << /Font << /F1 3 0 R "
                f"/F2 4 0 R /F3 5 0 R >> >>{annots_str} "
                f"/Contents {content_object_number} 0 R >>"
            ).encode("ascii")
        )
        stream = "\n".join(_pdf_draw_command(item) for item in page).encode(
            "cp1252", errors="replace"
        )
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
        for lnk in links:
            escaped_url = lnk.url.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            objects.append(
                (
                    f"<< /Type /Annot /Subtype /Link "
                    f"/Rect [{lnk.x_start:.1f} {lnk.y_bottom:.1f} {lnk.x_end:.1f} {lnk.y_top:.1f}] "
                    f"/Border [0 0 0] "
                    f"/A << /Type /Action /S /URI /URI ({escaped_url}) >> >>"
                ).encode("ascii")
            )

    objects[1] = (
        f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>"
    ).encode("ascii")
    _write_pdf_objects(pdf_path, [item for item in objects if item is not None])


def _pdf_draw_command(item: _PdfDrawOp) -> str:
    if isinstance(item, _PdfRule):
        return (
            f"{item.line_width:.2f} w {item.x_start:.1f} {item.y_position:.1f} m "
            f"{item.x_end:.1f} {item.y_position:.1f} l S"
        )
    if isinstance(item, _PdfDot):
        radius = item.radius
        kappa = 0.55228475 * radius
        x_position = item.x_position
        y_position = item.y_position
        return (
            f"{x_position + radius:.2f} {y_position:.2f} m "
            f"{x_position + radius:.2f} {y_position + kappa:.2f} "
            f"{x_position + kappa:.2f} {y_position + radius:.2f} "
            f"{x_position:.2f} {y_position + radius:.2f} c "
            f"{x_position - kappa:.2f} {y_position + radius:.2f} "
            f"{x_position - radius:.2f} {y_position + kappa:.2f} "
            f"{x_position - radius:.2f} {y_position:.2f} c "
            f"{x_position - radius:.2f} {y_position - kappa:.2f} "
            f"{x_position - kappa:.2f} {y_position - radius:.2f} "
            f"{x_position:.2f} {y_position - radius:.2f} c "
            f"{x_position + kappa:.2f} {y_position - radius:.2f} "
            f"{x_position + radius:.2f} {y_position - kappa:.2f} "
            f"{x_position + radius:.2f} {y_position:.2f} c f"
        )
    return (
        f"BT /{item.font_name} {item.font_size:.1f} Tf "
        f"{item.x_position:.1f} {item.y_position:.1f} Td "
        f"({_escape_pdf_text(item.text)}) Tj ET"
    )


def _pdf_text_width(text: str, font_size: float, font_name: str = "F1") -> float:
    if not text:
        return 0.0
    width_factor = {"F1": 0.46, "F2": 0.5, "F3": 0.44}.get(font_name, 0.46)
    narrow_chars = sum(1 for char in text if char in " .,;:|!/ilI[]()")
    wide_chars = sum(1 for char in text if char in "MW@#%&")
    adjusted_length = len(text) - (narrow_chars * 0.28) + (wide_chars * 0.28)
    return max(0.0, adjusted_length * font_size * width_factor)


def _clip_pdf_text(text: str, width_points: float, font_size: float, font_name: str) -> str:
    if _pdf_text_width(text, font_size, font_name) <= width_points:
        return text
    clipped = text
    while clipped and _pdf_text_width(f"{clipped}...", font_size, font_name) > width_points:
        clipped = clipped[:-1]
    return f"{clipped.rstrip()}..." if clipped else ""


def _wrap_pdf_text(text: str, *, width_points: float, font_size: float) -> list[str]:
    normalized = " ".join(text.split())
    average_char_width = max(3.8, font_size * 0.47)
    character_width = max(24, int(width_points / average_char_width))
    return textwrap.wrap(
        normalized,
        width=character_width,
        break_long_words=True,
        replace_whitespace=True,
    ) or [normalized]


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
