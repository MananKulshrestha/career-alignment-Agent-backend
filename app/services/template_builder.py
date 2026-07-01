from __future__ import annotations

import re

from app.schemas.profile import ProfileItemRead
from app.schemas.resume import ContentType, TemplatePlaceholder, TemplatePlan
from app.schemas.selection import SectionEntrySelection, SelectionPlan
from app.services.validation import validate_selection_source_ids


def build_template_plan(
    selection_plan: SelectionPlan, profile_items: list[ProfileItemRead]
) -> TemplatePlan:
    source_ids = {item.source_item_id for item in profile_items}
    validate_selection_source_ids(selection_plan, source_ids)

    profile_by_source_id = {item.source_item_id: item for item in profile_items}
    placeholders: list[TemplatePlaceholder] = []
    for section in selection_plan.section_order:
        entries = selection_plan.selected_entries.get(section) or [
            SectionEntrySelection(source_item_id=source_item_id)
            for source_item_id in selection_plan.selected_item_ids.get(section, [])
        ]
        for entry in entries:
            item = profile_by_source_id.get(entry.source_item_id)
            if not item:
                continue
            placeholders.extend(
                _build_entry_placeholders(
                    section=section,
                    entry=entry,
                    item=item,
                    one_page=selection_plan.page_target == "one_page",
                )
            )

    return TemplatePlan(
        template_family=selection_plan.template_family,
        page_target=selection_plan.page_target,
        section_order=selection_plan.section_order,
        placeholders=placeholders,
    )


def _build_entry_placeholders(
    *,
    section: str,
    entry: SectionEntrySelection,
    item: ProfileItemRead,
    one_page: bool,
) -> list[TemplatePlaceholder]:
    source_item_id = entry.source_item_id
    safe_id = _safe_placeholder_segment(source_item_id)
    entry_id = f"{section}_{safe_id}"
    bullet_count = (
        entry.bullet_count if entry.bullet_count is not None else _default_bullets(section)
    )
    bullet_words = 24 if one_page else 32

    placeholders: list[TemplatePlaceholder] = []

    if section == "experience":
        placeholders.extend(
            [
                _placeholder(
                    section, entry_id, source_item_id, "title", ContentType.ENTRY_TITLE, 12
                ),
                _placeholder(
                    section,
                    entry_id,
                    source_item_id,
                    "organization",
                    ContentType.ENTRY_ORGANIZATION,
                    12,
                    required=False,
                ),
                _placeholder(
                    section,
                    entry_id,
                    source_item_id,
                    "location",
                    ContentType.LOCATION,
                    10,
                    required=False,
                ),
                _placeholder(
                    section,
                    entry_id,
                    source_item_id,
                    "dates",
                    ContentType.DATE_RANGE,
                    10,
                    required=False,
                ),
            ]
        )
    elif section == "projects":
        placeholders.extend(
            [
                _placeholder(
                    section, entry_id, source_item_id, "name", ContentType.ENTRY_TITLE, 10
                ),
                _placeholder(
                    section,
                    entry_id,
                    source_item_id,
                    "tech_stack",
                    ContentType.TECH_STACK,
                    18,
                    required=False,
                ),
                _placeholder(
                    section,
                    entry_id,
                    source_item_id,
                    "dates",
                    ContentType.DATE_RANGE,
                    10,
                    required=False,
                ),
            ]
        )
    elif section == "education":
        placeholders.extend(
            [
                _placeholder(
                    section,
                    entry_id,
                    source_item_id,
                    "school",
                    ContentType.ENTRY_ORGANIZATION,
                    14,
                ),
                _placeholder(
                    section, entry_id, source_item_id, "degree", ContentType.ENTRY_TITLE, 18
                ),
                _placeholder(
                    section,
                    entry_id,
                    source_item_id,
                    "location",
                    ContentType.LOCATION,
                    10,
                    required=False,
                ),
                _placeholder(
                    section,
                    entry_id,
                    source_item_id,
                    "dates",
                    ContentType.DATE_RANGE,
                    10,
                    required=False,
                ),
            ]
        )
    elif section == "technical_skills":
        label = item.payload.skill_category or item.payload.title or "Skills"
        placeholders.append(
            _placeholder(
                section,
                entry_id,
                source_item_id,
                "skill_list",
                ContentType.SKILL_LIST,
                50,
                field_label=label,
            )
        )
    elif section in {"achievements", "certifications"}:
        placeholders.extend(
            [
                _placeholder(
                    section, entry_id, source_item_id, "title", ContentType.ENTRY_TITLE, 18
                ),
                _placeholder(
                    section,
                    entry_id,
                    source_item_id,
                    "organization",
                    ContentType.ENTRY_ORGANIZATION,
                    12,
                    required=False,
                ),
                _placeholder(
                    section,
                    entry_id,
                    source_item_id,
                    "dates",
                    ContentType.DATE_RANGE,
                    10,
                    required=False,
                ),
            ]
        )
    elif section == "summary":
        placeholders.append(
            _placeholder(section, entry_id, source_item_id, "summary", ContentType.SUMMARY, 60)
        )

    for index in range(1, bullet_count + 1):
        placeholders.append(
            _placeholder(
                section,
                entry_id,
                source_item_id,
                f"bullet_{index}",
                ContentType.RESUME_BULLET,
                bullet_words,
            )
        )

    return placeholders


def _placeholder(
    section: str,
    entry_id: str,
    source_item_id: str,
    suffix: str,
    content_type: ContentType,
    max_words: int,
    *,
    required: bool = True,
    field_label: str | None = None,
) -> TemplatePlaceholder:
    return TemplatePlaceholder(
        placeholder_id=f"{entry_id}_{suffix}",
        source_item_id=source_item_id,
        max_words=max_words,
        content_type=content_type,
        section=section,
        entry_id=entry_id,
        field_label=field_label,
        required=required,
    )


def _default_bullets(section: str) -> int:
    if section in {"experience", "projects"}:
        return 2
    if section in {"achievements", "certifications", "summary"}:
        return 1
    return 0


def _safe_placeholder_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "item"
