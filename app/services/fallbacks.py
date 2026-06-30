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
from app.schemas.profile import ProfileItemRead, UserPreference
from app.schemas.resume import (
    ClaimStrength,
    PlaceholderValue,
    ResumeContent,
    ResumeWarning,
    ResumeWarningType,
    TemplatePlan,
)
from app.schemas.selection import (
    MissingRequirement,
    RequirementSupportStatus,
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
    return SelectionPlan(
        section_order=section_order or ["education", "projects", "technical_skills"],
        selected_item_ids=selected,
        reasons=reasons,
        target_keywords_covered=[
            skill.name
            for skill in job_spec.required_skills
            if skill.name.lower() not in missing_names
        ],
        missing_requirements=missing,
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
        base = item.payload.description.strip().split(".")[0]
        words = base.split()[: placeholder.max_words]
        values.append(
            PlaceholderValue(
                placeholder_id=placeholder.placeholder_id,
                text=" ".join(words).rstrip(".") + ".",
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
