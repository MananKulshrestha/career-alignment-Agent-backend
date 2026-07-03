from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.core.enums import ExtractionRisk, RemotePolicy, RequirementType, Seniority
from app.schemas.job_spec import (
    ExtractionMetadata,
    JobConstraints,
    JobSalary,
    JobSpec,
    SkillRequirement,
    TextRequirement,
)
from app.schemas.match import AdjacentEvidence, MatchAnalysis, RequirementGap
from app.schemas.profile import ProfileItemKind, ProfileItemPayload, ProfileItemRead, UserPreference
from app.schemas.profile_document import (
    ExcludedClaim,
    ExtractedProfileDraft,
    ExtractionProvenance,
    ExtractionSupportLevel,
    ExtractionWarning,
    ProfileDocumentExtraction,
    ReviewRecommendation,
    SourceDocumentKind,
    UnresolvedQuestion,
    WarningSeverity,
)
from app.schemas.resume import (
    ClaimStrength,
    ContentType,
    PlaceholderValue,
    ResumeContent,
    ResumeWarning,
    ResumeWarningType,
    TemplatePlan,
)
from app.schemas.selection import (
    ImprovementSuggestionCategory,
    ImprovementSuggestionSeverity,
    MissingRequirement,
    RequirementSupportStatus,
    ResumeImprovementSuggestion,
    SectionEntrySelection,
    SelectionPlan,
    SelectionReason,
)

COMMON_SKILLS = [
    "Python",
    "FastAPI",
    "Django",
    "Flask",
    "React",
    "Next.js",
    "TypeScript",
    "JavaScript",
    "PostgreSQL",
    "SQL",
    "Docker",
    "Kubernetes",
    "AWS",
    "Azure",
    "GCP",
    "Redis",
    "GraphQL",
    "REST",
    "Machine Learning",
    "LLM",
    "Pydantic",
]


def fallback_profile_document_extraction(
    *,
    document_kind: SourceDocumentKind,
    text: str,
    model_name: str = "deterministic-fallback",
) -> ProfileDocumentExtraction:
    del model_name
    lower_text = text.lower()
    skills = [skill for skill in COMMON_SKILLS if skill.lower() in lower_text]
    snippets = _document_snippets(text)
    drafts: list[ExtractedProfileDraft] = []
    excluded_claims: list[ExcludedClaim] = []
    document_warnings = [
        ExtractionWarning(
            code="deterministic_fallback",
            message="LLM extraction is disabled; drafts are conservative and require review.",
            severity=WarningSeverity.INFO,
        )
    ]

    if skills:
        drafts.append(
            ExtractedProfileDraft(
                draft_id="draft_skill_extracted_skills",
                kind=ProfileItemKind.SKILL,
                source_item_id="doc_skill_extracted_skills",
                payload=ProfileItemPayload(
                    title="Extracted Skills",
                    skill_category="Extracted Skills",
                    description=f"Skills mentioned in uploaded document: {', '.join(skills)}.",
                    skills=skills,
                    evidence_source=(
                        "Listed in uploaded source document; confirm practical evidence."
                    ),
                ),
                confidence=0.45,
                support_level=ExtractionSupportLevel.LISTED_ONLY,
                review_recommendation=ReviewRecommendation.ASK_USER,
                provenance=[
                    ExtractionProvenance(
                        locator="document text",
                        section_label="detected skills",
                        source_snippet=_snippet_for_terms(text, skills) or snippets[0],
                        confidence=0.45,
                    )
                ],
                warnings=[
                    ExtractionWarning(
                        code="listed_only_skills",
                        message=(
                            "Skills found by deterministic fallback are listed evidence only "
                            "until tied to a project, job, or credential."
                        ),
                        severity=WarningSeverity.MEDIUM,
                        field_name="skills",
                    )
                ],
            )
        )

    if _looks_like_project_text(lower_text):
        project_skills = skills[:8]
        title = _extract_labelled_value(text, ("project", "project name")) or "Uploaded Project"
        drafts.append(
            ExtractedProfileDraft(
                draft_id="draft_project_uploaded_project",
                kind=ProfileItemKind.PROJECT,
                source_item_id="doc_project_uploaded_project",
                payload=ProfileItemPayload(
                    title=title[:120],
                    description=_first_useful_sentence(text),
                    skills=project_skills,
                    tech_stack=project_skills,
                ),
                confidence=0.55,
                support_level=ExtractionSupportLevel.INFERRED,
                review_recommendation=ReviewRecommendation.NEEDS_EDIT,
                provenance=[
                    ExtractionProvenance(
                        locator="document text",
                        section_label="project-like text",
                        source_snippet=snippets[0],
                        confidence=0.55,
                    )
                ],
                warnings=[
                    ExtractionWarning(
                        code="project_needs_review",
                        message="Confirm project title, ownership, dates, and measurable impact.",
                        severity=WarningSeverity.MEDIUM,
                    )
                ],
            )
        )

    if document_kind == SourceDocumentKind.CERTIFICATION or "certification" in lower_text:
        cert_title = _extract_labelled_value(text, ("certification", "certificate")) or (
            "Uploaded Certification"
        )
        drafts.append(
            ExtractedProfileDraft(
                draft_id="draft_certification_uploaded_certification",
                kind=ProfileItemKind.CERTIFICATION,
                source_item_id="doc_certification_uploaded_certification",
                payload=ProfileItemPayload(
                    title=cert_title[:120],
                    description=_first_useful_sentence(text),
                    issuer=_extract_labelled_value(text, ("issuer", "issued by")),
                ),
                confidence=0.5,
                support_level=ExtractionSupportLevel.INFERRED,
                review_recommendation=ReviewRecommendation.NEEDS_EDIT,
                provenance=[
                    ExtractionProvenance(
                        locator="document text",
                        section_label="certification-like text",
                        source_snippet=snippets[0],
                        confidence=0.5,
                    )
                ],
                warnings=[
                    ExtractionWarning(
                        code="certification_needs_details",
                        message="Confirm issuer, credential date, URL, and criteria.",
                        severity=WarningSeverity.MEDIUM,
                    )
                ],
            )
        )

    if "kubernetes" in lower_text and "teammate" in lower_text:
        excluded_claims.append(
            ExcludedClaim(
                claim="Kubernetes ownership",
                reason=(
                    "The source mentions Kubernetes near teammate ownership; this is not "
                    "safe direct user evidence without confirmation."
                ),
                provenance=[
                    ExtractionProvenance(
                        locator="document text",
                        source_snippet=_snippet_for_terms(text, ["Kubernetes", "teammate"])
                        or snippets[0],
                        confidence=0.75,
                    )
                ],
                severity=WarningSeverity.HIGH,
            )
        )

    if not drafts:
        document_warnings.append(
            ExtractionWarning(
                code="no_profile_drafts",
                message="No obvious profile evidence was found by deterministic fallback.",
                severity=WarningSeverity.MEDIUM,
            )
        )

    return ProfileDocumentExtraction(
        detected_document_kind=document_kind,
        document_summary=_first_useful_sentence(text)[:600],
        overall_confidence=0.45 if drafts else 0.2,
        extraction_risk="medium" if drafts else "high",
        draft_items=drafts,
        excluded_claims=excluded_claims,
        document_warnings=document_warnings,
        unresolved_questions=[
            UnresolvedQuestion(
                field_name="profile_evidence",
                question="Which extracted drafts are accurate enough to save to your profile?",
                priority="high",
            )
        ],
    )


def _document_snippets(text: str) -> list[str]:
    snippets = [line.strip() for line in text.splitlines() if len(line.strip()) >= 20]
    if not snippets:
        snippets = [text.strip()]
    return [snippet[:600] for snippet in snippets if snippet.strip()] or ["Uploaded document text"]


def _snippet_for_terms(text: str, terms: list[str]) -> str | None:
    lower_text = text.lower()
    for term in terms:
        index = lower_text.find(term.lower())
        if index >= 0:
            start = max(0, index - 160)
            end = min(len(text), index + 240)
            return " ".join(text[start:end].split())
    return None


def _first_useful_sentence(text: str) -> str:
    normalized = " ".join(text.split())
    for separator in (". ", "\n"):
        parts = [part.strip(" .") for part in normalized.split(separator) if part.strip()]
        for part in parts:
            if len(part) >= 20:
                return part[:500]
    return normalized[:500] or "Uploaded source document evidence."


def _extract_labelled_value(text: str, labels: tuple[str, ...]) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        for label in labels:
            if lowered.startswith(label.lower()):
                _, _, value = stripped.partition(":")
                if value.strip():
                    return value.strip()
    return None


def _looks_like_project_text(lower_text: str) -> bool:
    return any(
        signal in lower_text
        for signal in (
            "project",
            "built ",
            "developed ",
            "implemented ",
            "designed ",
            "deployed ",
        )
    )


def infer_title_and_company(text: str) -> tuple[str, str]:
    lines = [line.strip(" #:-") for line in text.splitlines() if line.strip()]
    title = lines[0] if lines else "Unknown role"
    company = "Unknown company"
    for line in lines[:20]:
        lower = line.lower()
        if lower.startswith("company"):
            company = line.split(":", 1)[-1].strip() or company
        elif " at " in line and company == "Unknown company":
            maybe_title, maybe_company = line.split(" at ", 1)
            title = maybe_title.strip() or title
            company = maybe_company.strip() or company
    return title[:160], company[:160]


def fallback_job_spec(
    source_url: str, text: str, model_name: str = "deterministic-fallback"
) -> JobSpec:
    title, company = infer_title_and_company(text)
    lower_text = text.lower()
    skills = [
        SkillRequirement(
            name=skill,
            requirement_type=RequirementType.EXPLICIT
            if skill.lower() in lower_text
            else RequirementType.INFERRED,
            source_section=None,
            source_snippet=skill if skill.lower() in lower_text else None,
            confidence=0.75 if skill.lower() in lower_text else 0.25,
        )
        for skill in COMMON_SKILLS
        if skill.lower() in lower_text
    ]
    if not skills:
        skills = [
            SkillRequirement(
                name="Role-specific experience",
                requirement_type=RequirementType.UNCERTAIN,
                source_snippet=text[:240],
                confidence=0.2,
            )
        ]

    sentences = [
        part.strip() for part in text.replace("\n", " ").split(".") if len(part.strip()) > 25
    ]
    responsibilities = [
        TextRequirement(text=sentence[:280], source_snippet=sentence[:280], confidence=0.55)
        for sentence in sentences[:5]
    ] or [
        TextRequirement(
            text="Deliver responsibilities described in the job posting.",
            source_snippet=text[:240],
            confidence=0.2,
        )
    ]
    qualifications = [
        TextRequirement(text=sentence[:280], source_snippet=sentence[:280], confidence=0.55)
        for sentence in sentences[5:10]
    ] or [
        TextRequirement(
            text="Meet qualifications described in the job posting.",
            source_snippet=text[:240],
            confidence=0.2,
        )
    ]

    remote_policy = RemotePolicy.UNKNOWN
    if "remote" in lower_text:
        remote_policy = RemotePolicy.REMOTE
    elif "hybrid" in lower_text:
        remote_policy = RemotePolicy.HYBRID
    elif "onsite" in lower_text or "on-site" in lower_text:
        remote_policy = RemotePolicy.ONSITE

    seniority = Seniority.UNKNOWN
    if "intern" in lower_text:
        seniority = Seniority.INTERNSHIP
    elif "entry" in lower_text or "junior" in lower_text:
        seniority = Seniority.ENTRY
    elif "senior" in lower_text or "lead" in lower_text:
        seniority = Seniority.SENIOR
    elif "mid" in lower_text:
        seniority = Seniority.MID

    risk = ExtractionRisk.MEDIUM if company == "Unknown company" else ExtractionRisk.LOW
    return JobSpec(
        job_id=str(uuid4()),
        source_url=source_url,
        title=title,
        company=company,
        remote_policy=remote_policy,
        seniority=seniority,
        required_skills=skills,
        responsibilities=responsibilities,
        qualifications=qualifications,
        ats_keywords=[skill.name for skill in skills],
        constraints=JobConstraints(),
        salary=JobSalary(),
        extraction=ExtractionMetadata(
            risk=risk,
            model=model_name,
            verified=True,
            parsed_at=datetime.now(timezone.utc),
        ),
        parsed_markdown=text,
        raw_text_fallback=text,
    )


def deterministic_match(
    job_spec: JobSpec,
    profile_items: list[ProfileItemRead],
    preferences: UserPreference,
) -> MatchAnalysis:
    profile_chunks: list[str] = []
    for item in profile_items:
        profile_chunks.extend(
            [
                item.payload.description,
                " ".join(item.payload.skills),
                " ".join(item.payload.achievements),
                " ".join(item.payload.metrics),
            ]
        )
    profile_text = " ".join(profile_chunks).lower()
    required = [skill.name for skill in job_spec.required_skills]
    covered = [skill for skill in required if skill.lower() in profile_text]
    missing = [skill for skill in required if skill.lower() not in profile_text]

    preference_failures: list[str] = []
    if preferences.excluded_keywords:
        for keyword in preferences.excluded_keywords:
            if keyword.lower() in job_spec.parsed_markdown.lower():
                preference_failures.append(f"Posting contains excluded keyword: {keyword}")

    skill_score = len(covered) / max(len(required), 1)
    penalty = min(len(preference_failures) * 0.2, 0.5)
    score = max(0.0, min(1.0, (0.2 + 0.8 * skill_score) - penalty))

    if preference_failures:
        verdict = "rejected"
    elif score >= 0.78:
        verdict = "strong"
    elif score >= 0.55:
        verdict = "good"
    elif score >= preferences.match_threshold:
        verdict = "weak"
    else:
        verdict = "rejected"

    gaps = [
        RequirementGap(
            requirement=skill,
            adjacent_evidence_item_ids=[],
            resume_policy=f"Do not claim {skill}; mention only supported adjacent experience.",
        )
        for skill in missing
    ]
    adjacent = [
        AdjacentEvidence(
            requirement=skill,
            item_ids=[],
            explanation="No direct profile evidence was found by deterministic matching.",
        )
        for skill in missing[:5]
    ]
    return MatchAnalysis(
        match_score=round(score, 2),
        match_verdict=verdict,
        preference_failures=preference_failures,
        missing_requirements=gaps,
        adjacent_evidence=adjacent,
        short_explanation=f"Matched {len(covered)} of {len(required)} required skill signals.",
    )


def deterministic_selection(
    job_spec: JobSpec, profile_items: list[ProfileItemRead]
) -> SelectionPlan:
    selected: dict[str, list[str]] = {
        "education": [],
        "experience": [],
        "projects": [],
        "technical_skills": [],
        "achievements": [],
        "certifications": [],
    }
    reasons: list[SelectionReason] = []
    required_text = " ".join(skill.name.lower() for skill in job_spec.required_skills)

    for item in profile_items:
        section = {
            "education": "education",
            "experience": "experience",
            "project": "projects",
            "achievement": "achievements",
            "certification": "certifications",
            "skill": "technical_skills",
        }.get(item.kind)
        if not section:
            continue
        item_text = f"{item.payload.description} {' '.join(item.payload.skills)}".lower()
        if any(token in item_text for token in required_text.split()) or len(selected[section]) < 2:
            selected[section].append(item.source_item_id)
            reasons.append(
                SelectionReason(
                    item_id=item.source_item_id,
                    reason=(
                        "Selected because it is among the strongest available "
                        "profile evidence for this role."
                    ),
                )
            )

    selected = {section: ids for section, ids in selected.items() if ids}
    section_order = [
        section
        for section in [
            "education",
            "experience",
            "projects",
            "technical_skills",
            "achievements",
            "certifications",
        ]
        if section in selected
    ]
    profile_text = " ".join(
        f"{item.payload.description} {' '.join(item.payload.skills)}" for item in profile_items
    ).lower()
    missing = [
        MissingRequirement(
            requirement=skill.name,
            status=RequirementSupportStatus.NOT_SUPPORTED,
            adjacent_evidence_item_ids=[],
            resume_policy=f"Do not claim {skill.name} unless the user adds supporting evidence.",
        )
        for skill in job_spec.required_skills
        if skill.name.lower() not in profile_text
    ]
    missing_names = {gap.requirement.lower() for gap in missing}
    selected_entries = {
        section: [
            SectionEntrySelection(
                source_item_id=source_item_id,
                bullet_count=2 if section in {"experience", "projects"} else 0,
            )
            for source_item_id in source_ids
        ]
        for section, source_ids in selected.items()
    }
    suggestions = [
        ResumeImprovementSuggestion(
            severity=ImprovementSuggestionSeverity.WARNING,
            category=ImprovementSuggestionCategory.UNSUPPORTED_REQUIREMENT,
            message=f"No direct profile evidence was found for {gap.requirement}.",
            action=(
                "Add a project, job responsibility, certification, or measurable example "
                "before claiming this requirement."
            ),
            requirement=gap.requirement,
        )
        for gap in missing
    ]
    return SelectionPlan(
        section_order=section_order or ["education", "projects", "technical_skills"],
        selected_item_ids=selected,
        selected_entries=selected_entries,
        reasons=reasons,
        target_keywords_covered=[
            skill.name
            for skill in job_spec.required_skills
            if skill.name.lower() not in missing_names
        ],
        missing_requirements=missing,
        user_improvement_suggestions=suggestions,
    )


def deterministic_resume_content(
    template_plan: TemplatePlan, profile_items: list[ProfileItemRead]
) -> ResumeContent:
    by_source_id = {item.source_item_id: item for item in profile_items}
    values: list[PlaceholderValue] = []
    for placeholder in template_plan.placeholders:
        item = by_source_id.get(placeholder.source_item_id)
        if not item:
            continue
        base = _deterministic_placeholder_text(placeholder, item)
        words = base.split()[: placeholder.max_words]
        values.append(
            PlaceholderValue(
                placeholder_id=placeholder.placeholder_id,
                text=_finalize_placeholder_text(" ".join(words), placeholder.content_type),
                source_item_ids=[item.source_item_id],
                claim_strength=ClaimStrength.BALANCED,
            )
        )
    return ResumeContent(
        placeholder_values=values,
        warnings=[
            ResumeWarning(
                type=ResumeWarningType.USER_REVIEW,
                message="Generated with deterministic fallback because LLM generation is disabled.",
            )
        ],
    )


def _deterministic_placeholder_text(placeholder, item: ProfileItemRead) -> str:
    payload = item.payload
    section = placeholder.section or placeholder.placeholder_id.split("_", 1)[0]

    if placeholder.content_type == ContentType.ENTRY_TITLE:
        if section == "education":
            return payload.degree or payload.title or _fallback_title(payload.description)
        if section == "experience":
            return payload.job_title or payload.title or _fallback_title(payload.description)
        return payload.title or _fallback_title(payload.description)

    if placeholder.content_type == ContentType.ENTRY_ORGANIZATION:
        if section == "education":
            return payload.school or payload.organization or ""
        if section == "experience":
            return payload.employer or payload.organization or ""
        return payload.issuer or payload.organization or ""

    if placeholder.content_type == ContentType.LOCATION:
        return payload.location or ""

    if placeholder.content_type == ContentType.DATE_RANGE:
        return _date_range(payload)

    if placeholder.content_type == ContentType.TECH_STACK:
        return _joined(payload.tech_stack or payload.skills or payload.tools_used)

    if placeholder.content_type == ContentType.SKILL_LIST:
        return _joined(payload.skills or payload.tools_used or payload.tech_stack)

    if placeholder.content_type == ContentType.SUMMARY:
        return payload.description.strip()

    if placeholder.content_type == ContentType.RESUME_BULLET:
        return _bullet_text(placeholder.placeholder_id, item)

    return payload.description.strip()


def _bullet_text(placeholder_id: str, item: ProfileItemRead) -> str:
    payload = item.payload
    index = _bullet_index(placeholder_id)
    if index == 1:
        return payload.description.strip().split(".")[0]

    candidates = [
        *payload.metrics,
        *payload.outcomes,
        payload.measurable_impact,
        *payload.achievements,
        *payload.responsibilities,
        *payload.features,
        payload.architecture,
        payload.constraints_tradeoffs,
    ]
    non_empty = [candidate for candidate in candidates if candidate and str(candidate).strip()]
    if index - 2 < len(non_empty):
        return str(non_empty[index - 2]).strip().rstrip(".")

    skills = payload.skills or payload.tech_stack or payload.tools_used
    if skills:
        return f"Used {', '.join(skills[:6])} to support the work"
    return payload.description.strip().split(".")[0]


def _bullet_index(placeholder_id: str) -> int:
    try:
        return int(placeholder_id.rsplit("_", 1)[-1])
    except ValueError:
        return 1


def _date_range(payload) -> str:
    if payload.credential_date:
        return _format_date(payload.credential_date)
    if payload.start_date and payload.end_date:
        return f"{_format_date(payload.start_date)} -- {_format_date(payload.end_date)}"
    if payload.start_date:
        return f"{_format_date(payload.start_date)} -- Present"
    if payload.end_date:
        return _format_date(payload.end_date)
    return ""


def _format_date(value) -> str:
    return value.strftime("%b %Y")


def _joined(values: list[str]) -> str:
    return ", ".join(value.strip() for value in values if value.strip())


def _fallback_title(description: str) -> str:
    words = description.strip().split()[:4]
    return " ".join(words) or "Profile Item"


def _finalize_placeholder_text(text: str, content_type: ContentType) -> str:
    clean = text.strip()
    if not clean:
        return ""
    if content_type == ContentType.RESUME_BULLET:
        return clean.rstrip(".") + "."
    return clean
