from app.schemas.profile import ProfileItemKind, ProfileItemPayload
from app.services.profile_service import add_kind_specific_evidence_gaps


def test_project_evidence_gaps_are_project_specific() -> None:
    payload = ProfileItemPayload(
        title="Job Tracker",
        description="Built a FastAPI job tracker.",
        skills=["FastAPI"],
    )

    updated = add_kind_specific_evidence_gaps(ProfileItemKind.PROJECT, payload)
    gap_fields = {gap.field_name for gap in updated.evidence_gaps}

    assert "problem" in gap_fields
    assert "target_users" in gap_fields
    assert "measurable_impact" in gap_fields
    assert "employer" not in gap_fields
    assert updated.problem is None


def test_experience_evidence_gaps_are_experience_specific() -> None:
    payload = ProfileItemPayload(
        title="Backend Intern",
        organization="ExampleCo",
        description="Supported backend API work.",
        skills=["Python"],
    )

    updated = add_kind_specific_evidence_gaps(ProfileItemKind.EXPERIENCE, payload)
    gap_fields = {gap.field_name for gap in updated.evidence_gaps}

    assert "team_scope" in gap_fields
    assert "responsibilities" in gap_fields
    assert "tools_used" not in gap_fields
    assert "target_users" not in gap_fields
    assert updated.team_scope is None


def test_education_skill_certification_and_achievement_gaps_are_kind_specific() -> None:
    education = add_kind_specific_evidence_gaps(
        ProfileItemKind.EDUCATION,
        ProfileItemPayload(
            title="BS Computer Science",
            organization="Example University",
            description="Studied computer science.",
        ),
    )
    skill = add_kind_specific_evidence_gaps(
        ProfileItemKind.SKILL,
        ProfileItemPayload(
            title="Frameworks",
            description="Backend framework skills.",
            skills=["FastAPI"],
        ),
    )
    certification = add_kind_specific_evidence_gaps(
        ProfileItemKind.CERTIFICATION,
        ProfileItemPayload(
            title="Cloud Practitioner",
            organization="Example Cloud",
            description="Completed a cloud certification.",
        ),
    )
    achievement = add_kind_specific_evidence_gaps(
        ProfileItemKind.ACHIEVEMENT,
        ProfileItemPayload(
            title="Hackathon Finalist",
            organization="Example Hackathon",
            description="Reached the final round.",
        ),
    )

    education_fields = {gap.field_name for gap in education.evidence_gaps}
    skill_fields = {gap.field_name for gap in skill.evidence_gaps}
    certification_fields = {gap.field_name for gap in certification.evidence_gaps}
    achievement_fields = {gap.field_name for gap in achievement.evidence_gaps}

    assert {"dates", "coursework", "honors"} <= education_fields
    assert {"proficiency", "evidence_source"} <= skill_fields
    assert {"credential_date", "credential_url", "criteria"} <= certification_fields
    assert {"credential_date", "criteria", "ranking_score"} <= achievement_fields
    assert education.coursework == []
    assert skill.proficiency is None
    assert certification.credential_url is None
    assert achievement.ranking_score is None


def test_research_note_evidence_gaps_are_research_specific() -> None:
    payload = ProfileItemPayload(
        title="Microsoft Explore internship research",
        description="Microsoft Explore emphasizes early CS exposure and collaborative learning.",
        source_name="Foundit article",
    )

    updated = add_kind_specific_evidence_gaps(ProfileItemKind.RESEARCH_NOTE, payload)
    gap_fields = {gap.field_name for gap in updated.evidence_gaps}

    assert {"source_url", "relevance", "limitations"} <= gap_fields
    assert "employer" not in gap_fields
    assert "tech_stack" not in gap_fields
    assert updated.key_findings == []
    assert updated.relevance is None
