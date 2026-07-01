from app.schemas.profile import ProfileItemKind, ProfileItemPayload, ProfileItemRead
from app.schemas.resume import ContentType
from app.schemas.selection import SectionEntrySelection, SelectionPlan
from app.services.template_builder import build_template_plan


def test_template_builder_creates_jake_style_placeholders_from_variable_counts() -> None:
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
        selected_entries={
            "projects": [
                SectionEntrySelection(source_item_id="project_1", bullet_count=3),
            ]
        },
    )

    plan = build_template_plan(selection, profile_items)

    assert plan.template_family == "jakes_resume"
    assert [placeholder.placeholder_id for placeholder in plan.placeholders] == [
        "projects_project_1_name",
        "projects_project_1_tech_stack",
        "projects_project_1_dates",
        "projects_project_1_bullet_1",
        "projects_project_1_bullet_2",
        "projects_project_1_bullet_3",
    ]
    assert plan.placeholders[0].content_type == ContentType.ENTRY_TITLE
    assert plan.placeholders[1].content_type == ContentType.TECH_STACK
    assert plan.placeholders[3].max_words == 24
    assert plan.latex_rules.allow_raw_latex_from_model is False
