from __future__ import annotations

from uuid import UUID

from sqlmodel import Session, select

from app.core.config import settings
from app.core.enums import TailoringStatus
from app.core.errors import BlockedWorkflowError
from app.models.tables import (
    CompileRun,
    JobSpecRecord,
    ResumeArtifact,
    TailoringSession,
    UserJobMatch,
    utc_now,
)
from app.schemas.api import TailoringSessionRead
from app.schemas.job_spec import JobSpec
from app.schemas.resume import CompileResult, ResumeContent, TemplatePlan
from app.schemas.selection import SelectionApproval, SelectionPlan
from app.services.agents import agent_gateway
from app.services.html_renderer import HTML_RENDERER_NAME, compile_resume
from app.services.job_ingestion import get_latest_job_spec_record
from app.services.model_run_logger import record_model_run
from app.services.profile_service import get_profile
from app.services.template_builder import build_template_plan
from app.services.validation import (
    validate_job_spec_handoff,
    validate_missing_requirements_preserved,
    validate_resume_content,
    validate_selection_source_ids,
)


async def create_tailoring_session(
    session: Session,
    *,
    user_id: UUID,
    job_id: UUID,
    revision_notes: str | None = None,
) -> TailoringSessionRead:
    spec_record = get_latest_job_spec_record(session, job_id)
    job_spec = JobSpec.model_validate(spec_record.structured_json)
    validate_job_spec_handoff(job_spec)
    profile = get_profile(session, user_id=user_id)
    if not profile.items:
        raise BlockedWorkflowError("resume tailoring requires at least one active profile item")
    selection_plan = await agent_gateway.create_selection_plan(
        job_spec=job_spec,
        profile_items=profile.items,
    )
    validate_selection_source_ids(selection_plan, {item.source_item_id for item in profile.items})

    record = TailoringSession(
        user_id=user_id,
        job_id=job_id,
        job_spec_id=spec_record.id,
        status=TailoringStatus.SELECTION_DRAFT.value,
        selection_plan=selection_plan.model_dump(mode="json"),
        revision_notes=revision_notes,
    )
    session.add(record)
    _update_match_tailoring_status(session, user_id, job_id, TailoringStatus.SELECTION_DRAFT)
    record_model_run(
        session,
        stage="selection_plan",
        model_name=settings.reliable_model if settings.llm_ready else "deterministic-fallback",
        user_id=user_id,
        job_id=job_id,
        input_summary={"profile_item_count": len(profile.items)},
        output_summary={"sections": selection_plan.section_order},
    )
    session.commit()
    session.refresh(record)
    return _session_read(record)


def approve_selection(
    session: Session,
    *,
    tailoring_session_id: UUID,
    approval: SelectionApproval,
) -> TailoringSessionRead:
    record = _get_tailoring_session(session, tailoring_session_id)
    if not approval.approved_by_user:
        raise BlockedWorkflowError("selection approval requires approved_by_user=true")
    if not record.selection_plan:
        raise BlockedWorkflowError("selection draft is missing")
    draft_selection_plan = SelectionPlan.model_validate(record.selection_plan)
    validate_missing_requirements_preserved(draft_selection_plan, approval.selection_plan)
    profile = get_profile(session, user_id=record.user_id)
    validate_selection_source_ids(
        approval.selection_plan, {item.source_item_id for item in profile.items}
    )
    template_plan = build_template_plan(approval.selection_plan, profile.items)
    record.confirmed_selection_plan = approval.selection_plan.model_dump(mode="json")
    record.template_plan = template_plan.model_dump(mode="json")
    record.status = TailoringStatus.SELECTION_APPROVED.value
    record.updated_at = utc_now()
    _update_match_tailoring_status(
        session,
        record.user_id,
        record.job_id,
        TailoringStatus.SELECTION_APPROVED,
    )
    session.commit()
    session.refresh(record)
    return _session_read(record)


async def generate_resume_content(
    session: Session,
    *,
    tailoring_session_id: UUID,
    revision_request: str | None = None,
) -> tuple[TailoringSessionRead, ResumeContent]:
    record = _get_tailoring_session(session, tailoring_session_id)
    if not record.confirmed_selection_plan or not record.template_plan:
        raise BlockedWorkflowError("selection must be approved before resume generation")

    spec_record = session.get(JobSpecRecord, record.job_spec_id)
    if not spec_record:
        raise BlockedWorkflowError("tailoring session job_spec not found")
    job_spec = JobSpec.model_validate(spec_record.structured_json)
    validate_job_spec_handoff(job_spec)
    selection_plan = SelectionPlan.model_validate(record.confirmed_selection_plan)
    template_plan = TemplatePlan.model_validate(record.template_plan)
    profile = get_profile(session, user_id=record.user_id)
    approved_ids = {
        source_id for ids in selection_plan.selected_item_ids.values() for source_id in ids
    }
    approved_items = [item for item in profile.items if item.source_item_id in approved_ids]
    content = await agent_gateway.write_resume_content(
        job_spec=job_spec,
        template_plan=template_plan,
        approved_profile_items=approved_items,
        revision_request=revision_request,
    )
    validate_resume_content(template_plan, content, approved_ids)

    record.resume_content = content.model_dump(mode="json")
    record.status = TailoringStatus.CONTENT_DRAFT.value
    record.updated_at = utc_now()
    _update_match_tailoring_status(
        session, record.user_id, record.job_id, TailoringStatus.CONTENT_DRAFT
    )
    record_model_run(
        session,
        stage="resume_content",
        model_name=settings.writing_model if settings.llm_ready else "deterministic-fallback",
        user_id=record.user_id,
        job_id=record.job_id,
        tailoring_session_id=record.id,
        input_summary={"approved_item_count": len(approved_items)},
        output_summary={"placeholder_count": len(content.placeholder_values)},
    )
    session.commit()
    session.refresh(record)
    return _session_read(record), content


def compile_tailored_resume(
    session: Session,
    *,
    tailoring_session_id: UUID,
) -> tuple[TailoringSessionRead, CompileResult]:
    record = _get_tailoring_session(session, tailoring_session_id)
    if not record.template_plan or not record.resume_content or not record.confirmed_selection_plan:
        raise BlockedWorkflowError("resume content must be generated before compilation")

    template_plan = TemplatePlan.model_validate(record.template_plan)
    resume_content = ResumeContent.model_validate(record.resume_content)
    selection_plan = SelectionPlan.model_validate(record.confirmed_selection_plan)
    profile = get_profile(session, user_id=record.user_id)
    approved_ids = {
        source_id for ids in selection_plan.selected_item_ids.values() for source_id in ids
    }
    approved_items = [item for item in profile.items if item.source_item_id in approved_ids]
    validate_resume_content(template_plan, resume_content, approved_ids)

    result = compile_resume(
        session_id=record.id,
        template_plan=template_plan,
        resume_content=resume_content,
        profile_items=approved_items,
    )
    record.status = (
        TailoringStatus.RENDERED.value if result.success else TailoringStatus.COMPILE_FAILED.value
    )
    record.updated_at = utc_now()
    _update_match_tailoring_status(
        session, record.user_id, record.job_id, TailoringStatus(record.status)
    )
    session.add(
        CompileRun(
            tailoring_session_id=record.id,
            success=result.success,
            compiler=HTML_RENDERER_NAME,
            tex_path=result.tex_path,
            pdf_path=result.pdf_path,
            log_path=result.log_path,
            page_count=result.page_count,
            compiler_output=result.compiler_output,
            repair_attempted=result.repair_attempted,
        )
    )
    if result.success:
        spec_record = get_latest_job_spec_record(session, record.job_id)
        session.add(
            ResumeArtifact(
                tailoring_session_id=record.id,
                job_id=record.job_id,
                user_id=record.user_id,
                pdf_path=result.pdf_path,
                tex_path=result.tex_path,
                log_path=result.log_path,
                job_spec_version=spec_record.version,
                selection_plan=selection_plan.model_dump(mode="json"),
                template_plan=template_plan.model_dump(mode="json"),
                resume_content=resume_content.model_dump(mode="json"),
                compile_metadata=result.model_dump(mode="json"),
                is_final=False,
            )
        )
    session.commit()
    session.refresh(record)
    return _session_read(record), result


def get_tailoring_session_read(
    session: Session, *, tailoring_session_id: UUID
) -> TailoringSessionRead:
    return _session_read(_get_tailoring_session(session, tailoring_session_id))


def approve_final_artifact(session: Session, *, tailoring_session_id: UUID) -> TailoringSessionRead:
    record = _get_tailoring_session(session, tailoring_session_id)
    if record.status != TailoringStatus.RENDERED.value:
        raise BlockedWorkflowError("final approval requires the latest compile to be rendered")
    artifact = session.exec(
        select(ResumeArtifact)
        .where(ResumeArtifact.tailoring_session_id == tailoring_session_id)
        .order_by(ResumeArtifact.created_at.desc())
    ).first()
    if not artifact:
        raise BlockedWorkflowError("cannot approve final resume before a successful compile")
    existing_finals = session.exec(
        select(ResumeArtifact).where(
            ResumeArtifact.tailoring_session_id == tailoring_session_id,
            ResumeArtifact.is_final == True,  # noqa: E712
        )
    ).all()
    for existing in existing_finals:
        existing.is_final = False
        existing.updated_at = utc_now()
    artifact.is_final = True
    artifact.updated_at = utc_now()
    record.status = TailoringStatus.FINAL_APPROVED.value
    record.updated_at = utc_now()
    _update_match_tailoring_status(
        session,
        record.user_id,
        record.job_id,
        TailoringStatus.FINAL_APPROVED,
    )
    session.commit()
    session.refresh(record)
    return _session_read(record)


def _get_tailoring_session(session: Session, tailoring_session_id: UUID) -> TailoringSession:
    record = session.get(TailoringSession, tailoring_session_id)
    if not record:
        raise BlockedWorkflowError("tailoring session not found")
    return record


def _update_match_tailoring_status(
    session: Session,
    user_id: UUID,
    job_id: UUID,
    status: TailoringStatus,
) -> None:
    match = session.exec(
        select(UserJobMatch).where(UserJobMatch.user_id == user_id, UserJobMatch.job_id == job_id)
    ).first()
    if match:
        match.tailoring_status = status.value
        match.updated_at = utc_now()


def _session_read(record: TailoringSession) -> TailoringSessionRead:
    current_selection_plan = record.confirmed_selection_plan or record.selection_plan
    return TailoringSessionRead(
        id=record.id,
        user_id=record.user_id,
        job_id=record.job_id,
        status=record.status,
        selection_plan=SelectionPlan.model_validate(current_selection_plan)
        if current_selection_plan
        else None,
        template_plan=TemplatePlan.model_validate(record.template_plan)
        if record.template_plan
        else None,
        resume_content=ResumeContent.model_validate(record.resume_content)
        if record.resume_content
        else None,
    )
