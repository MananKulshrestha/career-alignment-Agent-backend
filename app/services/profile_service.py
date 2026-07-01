from __future__ import annotations

from uuid import UUID

from sqlmodel import Session, select

from app.models.tables import UserProfileItem, utc_now
from app.schemas.profile import (
    EvidenceGap,
    EvidenceGapStatus,
    ProfileItemCreate,
    ProfileItemKind,
    ProfileItemPayload,
    ProfileItemRead,
    UserPreference,
    UserProfileRead,
)


def add_profile_item(
    session: Session, *, user_id: UUID, request: ProfileItemCreate
) -> ProfileItemRead:
    payload = add_kind_specific_evidence_gaps(request.kind, request.payload)
    existing = session.exec(
        select(UserProfileItem).where(
            UserProfileItem.user_id == user_id,
            UserProfileItem.source_item_id == request.source_item_id,
        )
    ).first()
    if existing:
        existing.kind = request.kind.value
        existing.payload = payload.model_dump(mode="json")
        existing.is_active = request.is_active
        existing.updated_at = utc_now()
        record = existing
    else:
        record = UserProfileItem(
            user_id=user_id,
            source_item_id=request.source_item_id,
            kind=request.kind.value,
            payload=payload.model_dump(mode="json"),
            is_active=request.is_active,
        )
        session.add(record)
    session.commit()
    session.refresh(record)
    return _profile_item_read(record)


def get_profile(
    session: Session,
    *,
    user_id: UUID,
    preferences: UserPreference | None = None,
) -> UserProfileRead:
    records = session.exec(
        select(UserProfileItem).where(
            UserProfileItem.user_id == user_id,
            UserProfileItem.is_active == True,  # noqa: E712
        )
    ).all()
    return UserProfileRead(
        user_id=str(user_id),
        preferences=preferences or UserPreference(),
        items=[_profile_item_read(record) for record in records],
    )


def _profile_item_read(record: UserProfileItem) -> ProfileItemRead:
    return ProfileItemRead(
        id=str(record.id),
        user_id=str(record.user_id),
        kind=record.kind,
        source_item_id=record.source_item_id,
        payload=record.payload,
        is_active=record.is_active,
    )


def add_kind_specific_evidence_gaps(
    kind: ProfileItemKind, payload: ProfileItemPayload
) -> ProfileItemPayload:
    """Persist explicit missingness so the UI can ask better follow-ups later."""

    generated = _generate_kind_specific_evidence_gaps(kind, payload)
    existing_by_field = {gap.field_name: gap for gap in payload.evidence_gaps}
    merged: list[EvidenceGap] = []
    generated_fields: set[str] = set()

    for gap in generated:
        generated_fields.add(gap.field_name)
        existing = existing_by_field.get(gap.field_name)
        if existing and existing.status != EvidenceGapStatus.MISSING:
            merged.append(existing)
        elif existing and existing.answer:
            merged.append(existing.model_copy(update={"status": EvidenceGapStatus.ANSWERED}))
        else:
            merged.append(gap)

    for gap in payload.evidence_gaps:
        if gap.field_name not in generated_fields:
            merged.append(gap)

    return payload.model_copy(update={"evidence_gaps": merged}, deep=True)


def _generate_kind_specific_evidence_gaps(
    kind: ProfileItemKind, payload: ProfileItemPayload
) -> list[EvidenceGap]:
    if kind == ProfileItemKind.PROJECT:
        checks = [
            (
                "title",
                _has_value(payload.title),
                "What is the project name exactly as it should appear on the resume?",
            ),
            (
                "problem",
                _has_value(payload.problem),
                "What problem did this project solve, and why was it worth building?",
            ),
            (
                "target_users",
                _has_value(payload.target_users),
                "Who used or would use this project?",
            ),
            (
                "role",
                _has_value(payload.role),
                "What was your specific role and ownership on this project?",
            ),
            (
                "tech_stack",
                _has_value(payload.tech_stack) or _has_value(payload.skills),
                "Which technologies did you actually use in the project?",
            ),
            (
                "architecture",
                _has_value(payload.architecture) or _has_value(payload.features),
                "What important features, architecture choices, or integrations did you build?",
            ),
            (
                "measurable_impact",
                _has_value(payload.measurable_impact) or _has_value(payload.metrics),
                (
                    "What measurable result, scale, adoption, performance, or quality impact "
                    "can you support?"
                ),
            ),
            (
                "repo_or_demo_url",
                (
                    _has_value(payload.repo_url)
                    or _has_value(payload.demo_url)
                    or _has_value(payload.url)
                ),
                "Is there a GitHub, demo, write-up, or portfolio URL for this project?",
            ),
            (
                "dates",
                _has_value(payload.start_date) or _has_value(payload.end_date),
                "When did you work on this project?",
            ),
            (
                "constraints_tradeoffs",
                _has_value(payload.constraints_tradeoffs),
                "What constraints, tradeoffs, or hard technical decisions shaped the project?",
            ),
        ]
    elif kind == ProfileItemKind.EXPERIENCE:
        checks = [
            (
                "employer",
                _has_value(payload.employer) or _has_value(payload.organization),
                "What employer or organization should be listed?",
            ),
            (
                "job_title",
                _has_value(payload.job_title) or _has_value(payload.title),
                "What was your official or best truthful role title?",
            ),
            (
                "location",
                _has_value(payload.location),
                "What location or remote/hybrid context should be listed?",
            ),
            (
                "dates",
                _has_value(payload.start_date) or _has_value(payload.end_date),
                "What were the start and end dates for this experience?",
            ),
            (
                "employment_type",
                _has_value(payload.employment_type),
                (
                    "Was this full-time, part-time, internship, contract, freelance, "
                    "or volunteer work?"
                ),
            ),
            (
                "team_scope",
                _has_value(payload.team_scope),
                "What team, product area, user base, or operational scope did you support?",
            ),
            (
                "responsibilities",
                _has_value(payload.responsibilities),
                "What responsibilities did you repeatedly own in this role?",
            ),
            (
                "tools_used",
                _has_value(payload.tools_used) or _has_value(payload.skills),
                "Which tools and technologies did you actually use on the job?",
            ),
            (
                "outcomes",
                _has_value(payload.outcomes) or _has_value(payload.metrics),
                "What measurable outcomes, improvements, or business impact can you support?",
            ),
            (
                "cross_functional_work",
                _has_value(payload.cross_functional_work),
                "Who did you collaborate with outside your immediate role or team?",
            ),
        ]
    elif kind == ProfileItemKind.EDUCATION:
        checks = [
            (
                "school",
                _has_value(payload.school) or _has_value(payload.organization),
                "What school should be listed?",
            ),
            (
                "degree",
                _has_value(payload.degree) or _has_value(payload.title),
                "What degree, program, or credential should be listed?",
            ),
            (
                "dates",
                _has_value(payload.start_date) or _has_value(payload.end_date),
                "What attendance or graduation dates should be listed?",
            ),
            (
                "coursework",
                _has_value(payload.coursework),
                "Which relevant coursework should be listed, if useful for this job?",
            ),
            (
                "honors",
                _has_value(payload.honors),
                "Are there honors, awards, scholarships, or GPA details worth listing?",
            ),
        ]
    elif kind == ProfileItemKind.SKILL:
        checks = [
            (
                "skill_category",
                _has_value(payload.skill_category) or _has_value(payload.title),
                (
                    "What skill category should this belong to, such as Languages, "
                    "Frameworks, or Tools?"
                ),
            ),
            (
                "skills",
                _has_value(payload.skills),
                "Which concrete skills belong in this category?",
            ),
            (
                "proficiency",
                _has_value(payload.proficiency),
                "What level or recency of practical experience do you have with these skills?",
            ),
            (
                "evidence_source",
                _has_value(payload.evidence_source),
                "Which project, job, or credential proves these skills?",
            ),
        ]
    elif kind == ProfileItemKind.CERTIFICATION:
        checks = [
            ("title", _has_value(payload.title), "What is the exact certification name?"),
            (
                "issuer",
                _has_value(payload.issuer) or _has_value(payload.organization),
                "Who issued the certification?",
            ),
            (
                "credential_date",
                _has_value(payload.credential_date) or _has_value(payload.start_date),
                "When was the certification issued or completed?",
            ),
            (
                "credential_url",
                _has_value(payload.credential_url) or _has_value(payload.url),
                "Is there a credential URL or verification ID?",
            ),
            (
                "criteria",
                _has_value(payload.criteria),
                "What exam, project, or criteria earned the certification?",
            ),
        ]
    elif kind == ProfileItemKind.ACHIEVEMENT:
        checks = [
            (
                "title",
                _has_value(payload.title),
                "What achievement, award, publication, or competition result should be listed?",
            ),
            (
                "issuer",
                _has_value(payload.issuer) or _has_value(payload.organization),
                "Who granted or recognized this achievement?",
            ),
            (
                "credential_date",
                _has_value(payload.credential_date) or _has_value(payload.start_date),
                "When did this achievement happen?",
            ),
            (
                "criteria",
                _has_value(payload.criteria),
                "What criteria, selection process, or work earned this achievement?",
            ),
            (
                "ranking_score",
                _has_value(payload.ranking_score),
                "Was there a ranking, score, acceptance rate, or other supported measure?",
            ),
        ]
    elif kind == ProfileItemKind.RESEARCH_NOTE:
        checks = [
            (
                "research_topic",
                _has_value(payload.research_topic) or _has_value(payload.title),
                "What job, company, domain, or role question does this research note cover?",
            ),
            (
                "source_name",
                _has_value(payload.source_name) or _has_value(payload.organization),
                (
                    "Where did this research come from, such as a job post, "
                    "company page, article, or call?"
                ),
            ),
            (
                "source_url",
                _has_value(payload.source_url) or _has_value(payload.url),
                "Is there a source URL or reference link for this research?",
            ),
            (
                "key_findings",
                _has_value(payload.key_findings) or _has_value(payload.description),
                "What are the concrete findings the resume or interview prep should use?",
            ),
            (
                "relevance",
                _has_value(payload.relevance),
                "Why is this research relevant to the target resume or job strategy?",
            ),
            (
                "limitations",
                _has_value(payload.limitations),
                "What is uncertain, time-sensitive, or not directly supported by this research?",
            ),
        ]
    else:
        checks = []

    return [
        EvidenceGap(field_name=field_name, question=question)
        for field_name, has_answer, question in checks
        if not has_answer
    ]


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_value(item) for item in value)
    return True
