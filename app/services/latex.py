from __future__ import annotations

from app.schemas.profile import ProfileItemRead
from app.schemas.resume import ContentType, ResumeContent, TemplatePlan

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
        elif section in {"education", "experience"}:
            lines.extend(
                _render_subheading_section(section, section_placeholders, content_by_placeholder)
            )
        elif section == "projects":
            lines.extend(
                _render_projects_section(
                    section_placeholders,
                    content_by_placeholder,
                    profile_by_id,
                )
            )
        elif section in {"achievements", "certifications"}:
            lines.extend(
                _render_project_like_section(
                    section,
                    section_placeholders,
                    content_by_placeholder,
                    profile_by_id,
                )
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
        title = _first_content(
            entry_placeholders, content_by_placeholder, ContentType.ENTRY_TITLE
        )
        organization = _first_content(
            entry_placeholders, content_by_placeholder, ContentType.ENTRY_ORGANIZATION
        )
        location = _first_content(entry_placeholders, content_by_placeholder, ContentType.LOCATION)
        dates = _first_content(entry_placeholders, content_by_placeholder, ContentType.DATE_RANGE)
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
    placeholders,
    content_by_placeholder: dict[str, str],
    profile_by_id: dict[str, ProfileItemRead],
) -> list[str]:
    lines = [r"\section{Projects}", r"    \resumeSubHeadingListStart"]
    for entry_placeholders in _group_by_entry(placeholders).values():
        title = _first_content(
            entry_placeholders, content_by_placeholder, ContentType.ENTRY_TITLE
        )
        tech_stack = _first_content(
            entry_placeholders, content_by_placeholder, ContentType.TECH_STACK
        )
        dates = _first_content(entry_placeholders, content_by_placeholder, ContentType.DATE_RANGE)
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
    section: str,
    placeholders,
    content_by_placeholder: dict[str, str],
    profile_by_id: dict[str, ProfileItemRead],
) -> list[str]:
    lines = [
        rf"\section{{{escape_latex(_section_label(section))}}}",
        r"    \resumeSubHeadingListStart",
    ]
    for entry_placeholders in _group_by_entry(placeholders).values():
        title = _first_content(
            entry_placeholders, content_by_placeholder, ContentType.ENTRY_TITLE
        )
        organization = _first_content(
            entry_placeholders, content_by_placeholder, ContentType.ENTRY_ORGANIZATION
        )
        dates = _first_content(entry_placeholders, content_by_placeholder, ContentType.DATE_RANGE)
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


def _get_entry_url_latex(source_item_id: str, profile_by_id: dict[str, ProfileItemRead]) -> str:
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


def _section_label(section: str) -> str:
    return section.replace("_", " ").title()
