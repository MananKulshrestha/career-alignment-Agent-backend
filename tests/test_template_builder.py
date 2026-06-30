from app.schemas.profile import ProfileItemKind, ProfileItemPayload, ProfileItemRead
from app.schemas.selection import SelectionPlan
from app.services.template_builder import build_template_plan


def test_template_builder_creates_bounded_placeholders() -> None:
    profile_items = [
        ProfileItemRead(
            id="1",
            user_id="user_1",
            kind=ProfileItemKind.PROJECT,
            source_item_id="project_1",
            payload=ProfileItemPayload(
                title="Job Tracker",
                description="Built a FastAPI job tracker with PostgreSQL.",
                skills=["FastAPI", "PostgreSQL"],
            ),
        )
    ]
    selection = SelectionPlan(
        section_order=["projects"],
        selected_item_ids={"projects": ["project_1"]},
    )

    plan = build_template_plan(selection, profile_items)

    assert len(plan.placeholders) == 2
    assert plan.placeholders[0].placeholder_id == "projects_project_1_bullet_1"
    assert plan.latex_rules.allow_raw_latex_from_model is False
