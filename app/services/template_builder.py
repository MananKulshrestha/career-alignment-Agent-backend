from __future__ import annotations

import re

from app.schemas.profile import ProfileItemRead
from app.schemas.resume import ContentType, TemplatePlaceholder, TemplatePlan
from app.schemas.selection import SelectionPlan
from app.services.validation import validate_selection_source_ids


def build_template_plan(
    selection_plan: SelectionPlan, profile_items: list[ProfileItemRead]
) -> TemplatePlan:
    source_ids = {item.source_item_id for item in profile_items}
    validate_selection_source_ids(selection_plan, source_ids)

    placeholders: list[TemplatePlaceholder] = []
    for section in selection_plan.section_order:
        for source_item_id in selection_plan.selected_item_ids.get(section, []):
            safe_id = _safe_placeholder_segment(source_item_id)
            bullet_count = 2 if section in {"experience", "projects"} else 1
            for index in range(1, bullet_count + 1):
                placeholders.append(
                    TemplatePlaceholder(
                        placeholder_id=f"{section}_{safe_id}_bullet_{index}",
                        source_item_id=source_item_id,
                        max_words=24 if selection_plan.page_target == "one_page" else 32,
                        content_type=ContentType.RESUME_BULLET,
                    )
                )

    return TemplatePlan(
        page_target=selection_plan.page_target,
        section_order=selection_plan.section_order,
        placeholders=placeholders,
    )


def _safe_placeholder_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "item"
