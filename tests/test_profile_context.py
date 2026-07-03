from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.errors import BlockedWorkflowError
from app.schemas.profile import (
    ProfileItemCreate,
    ProfileItemKind,
    ProfileItemPayload,
    ResumeStrictness,
    UserPreference,
    UserProfileContextUpsert,
)
from app.schemas.resume import (
    ContentType,
    PlaceholderValue,
    ResumeContent,
    TemplatePlaceholder,
    TemplatePlan,
)
from app.services.fallbacks import deterministic_match, fallback_job_spec
from app.services.profile_service import add_profile_item, get_profile, upsert_profile_context
from app.services.validation import validate_resume_content, validate_user_context_constraints


def test_profile_context_upsert_and_profile_read() -> None:
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    user_id = uuid4()

    with Session(engine) as session:
        assert get_profile(session, user_id=user_id).context is None

        created = upsert_profile_context(
            session,
            user_id=user_id,
            request=UserProfileContextUpsert(
                abstract="  Backend engineer focused on reliable APIs.  ",
                specializations=["FastAPI", "fastapi", "PostgreSQL"],
                target_roles=["Backend Engineer"],
                resume_strictness=ResumeStrictness.CONSERVATIVE,
                avoid_claims=["leadership"],
            ),
        )

        assert created.abstract == "Backend engineer focused on reliable APIs."
        assert created.specializations == ["FastAPI", "PostgreSQL"]
        assert created.resume_strictness == ResumeStrictness.CONSERVATIVE

        updated = upsert_profile_context(
            session,
            user_id=user_id,
            request=UserProfileContextUpsert(
                abstract="Platform API roles.",
                target_roles=["Platform Engineer"],
                resume_strictness=ResumeStrictness.ASSERTIVE,
            ),
        )
        profile = get_profile(session, user_id=user_id)

    assert updated.id == created.id
    assert profile.context is not None
    assert profile.context.abstract == "Platform API roles."
    assert profile.context.specializations == []
    assert profile.context.target_roles == ["Platform Engineer"]
    assert profile.items == []


def test_profile_context_rejects_ambiguous_or_unbounded_payloads() -> None:
    with pytest.raises(ValidationError):
        UserProfileContextUpsert(abstract="   ")

    with pytest.raises(ValidationError):
        UserProfileContextUpsert(specializations=[""])

    with pytest.raises(ValidationError):
        UserProfileContextUpsert(has_kubernetes=True)


def test_context_only_skill_does_not_count_as_deterministic_match_evidence() -> None:
    spec = fallback_job_spec(
        source_url="manual://kubernetes",
        text=(
            "Platform Engineer at ExampleCo\n"
            "Company: ExampleCo\n"
            "Required: Kubernetes. Build reliable platform automation."
        ),
    )
    profile_item = _project_item(
        source_item_id="project_fastapi",
        description="Built a FastAPI and PostgreSQL job tracker.",
        skills=["FastAPI", "PostgreSQL"],
    )
    context = UserProfileContextUpsert(
        abstract="I specialize in Kubernetes and distributed systems.",
        specializations=["Kubernetes"],
    )

    analysis = deterministic_match(
        spec,
        [profile_item],
        UserPreference(),
        user_context=context_to_read(context),
    )

    assert any(gap.requirement == "Kubernetes" for gap in analysis.missing_requirements)
    assert "Matched 0 of 1" in analysis.short_explanation


def test_context_only_term_cannot_leak_into_resume_content() -> None:
    profile_item = _project_item(
        source_item_id="project_fastapi",
        description="Built a FastAPI and PostgreSQL job tracker.",
        skills=["FastAPI", "PostgreSQL"],
    )
    template_plan = _single_bullet_template(profile_item.source_item_id)
    content = ResumeContent(
        placeholder_values=[
            PlaceholderValue(
                placeholder_id="projects_project_fastapi_bullet_1",
                text="Deployed Kubernetes workloads for reliable platform automation.",
                source_item_ids=[profile_item.source_item_id],
            )
        ]
    )
    context = context_to_read(
        UserProfileContextUpsert(
            abstract="I specialize in Kubernetes.",
            specializations=["Kubernetes"],
        )
    )

    validate_resume_content(template_plan, content, {profile_item.source_item_id})
    with pytest.raises(BlockedWorkflowError, match="context-only claim"):
        validate_user_context_constraints(content, [profile_item], context)


def test_context_term_is_allowed_when_cited_evidence_supports_it() -> None:
    profile_item = _project_item(
        source_item_id="project_kubernetes",
        description="Deployed Kubernetes workloads for a platform automation project.",
        skills=["Kubernetes"],
    )
    content = ResumeContent(
        placeholder_values=[
            PlaceholderValue(
                placeholder_id="projects_project_kubernetes_bullet_1",
                text="Deployed Kubernetes workloads for platform automation.",
                source_item_ids=[profile_item.source_item_id],
            )
        ]
    )
    context = context_to_read(UserProfileContextUpsert(specializations=["Kubernetes"]))

    validate_user_context_constraints(content, [profile_item], context)


def test_avoid_claims_block_generated_resume_text() -> None:
    profile_item = _project_item(
        source_item_id="project_fastapi",
        description="Built a FastAPI and PostgreSQL job tracker.",
        skills=["FastAPI", "PostgreSQL"],
    )
    content = ResumeContent(
        placeholder_values=[
            PlaceholderValue(
                placeholder_id="projects_project_fastapi_bullet_1",
                text="Led a team to build reliable FastAPI services.",
                source_item_ids=[profile_item.source_item_id],
            )
        ]
    )
    context = context_to_read(UserProfileContextUpsert(avoid_claims=["leadership"]))

    with pytest.raises(BlockedWorkflowError, match="avoided claim"):
        validate_user_context_constraints(content, [profile_item], context)


def test_profile_context_does_not_create_profile_items() -> None:
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    user_id = uuid4()

    with Session(engine) as session:
        add_profile_item(
            session,
            user_id=user_id,
            request=ProfileItemCreate(
                kind=ProfileItemKind.PROJECT,
                source_item_id="project_fastapi",
                payload=ProfileItemPayload(
                    title="FastAPI Tracker",
                    description="Built a FastAPI tracker.",
                    skills=["FastAPI"],
                ),
            ),
        )
        upsert_profile_context(
            session,
            user_id=user_id,
            request=UserProfileContextUpsert(abstract="Target backend roles."),
        )
        profile = get_profile(session, user_id=user_id)

    assert profile.context is not None
    assert [item.source_item_id for item in profile.items] == ["project_fastapi"]


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _project_item(
    *,
    source_item_id: str,
    description: str,
    skills: list[str],
):
    from app.schemas.profile import ProfileItemRead

    return ProfileItemRead(
        id=f"{source_item_id}_id",
        user_id="user_1",
        kind=ProfileItemKind.PROJECT,
        source_item_id=source_item_id,
        payload=ProfileItemPayload(
            title=source_item_id.replace("_", " ").title(),
            description=description,
            skills=skills,
        ),
    )


def _single_bullet_template(source_item_id: str) -> TemplatePlan:
    return TemplatePlan(
        section_order=["projects"],
        placeholders=[
            TemplatePlaceholder(
                placeholder_id=f"projects_{source_item_id}_bullet_1",
                source_item_id=source_item_id,
                content_type=ContentType.RESUME_BULLET,
            )
        ],
    )


def context_to_read(context: UserProfileContextUpsert):
    from app.schemas.profile import UserProfileContextRead

    return UserProfileContextRead(
        id="context_1",
        user_id="user_1",
        **context.model_dump(mode="json"),
    )
