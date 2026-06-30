from pathlib import Path
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import FileResponse
from sqlmodel import select

from app.api.deps import DbSession
from app.core.config import settings
from app.core.errors import http_not_found
from app.models.tables import ResumeArtifact
from app.schemas.api import (
    ResumeCompileResponse,
    ResumeGenerateRequest,
    ResumeGenerateResponse,
    SelectionApprovalRequest,
    TailoringSessionCreate,
    TailoringSessionRead,
)
from app.services.tailoring import (
    approve_final_artifact,
    approve_selection,
    compile_tailored_resume,
    create_tailoring_session,
    generate_resume_content,
    get_tailoring_session_read,
)

router = APIRouter()


@router.post("/sessions", response_model=TailoringSessionRead)
async def create_tailoring_session_route(
    request: TailoringSessionCreate,
    session: DbSession,
) -> TailoringSessionRead:
    return await create_tailoring_session(
        session,
        user_id=request.user_id,
        job_id=request.job_id,
        revision_notes=request.revision_notes,
    )


@router.get("/sessions/{session_id}", response_model=TailoringSessionRead)
def get_tailoring_session_route(session_id: UUID, session: DbSession) -> TailoringSessionRead:
    return get_tailoring_session_read(session, tailoring_session_id=session_id)


@router.post("/sessions/{session_id}/approve-selection", response_model=TailoringSessionRead)
def approve_selection_route(
    session_id: UUID,
    request: SelectionApprovalRequest,
    session: DbSession,
) -> TailoringSessionRead:
    return approve_selection(session, tailoring_session_id=session_id, approval=request)


@router.post("/sessions/{session_id}/generate", response_model=ResumeGenerateResponse)
async def generate_resume_route(
    session_id: UUID,
    request: ResumeGenerateRequest,
    session: DbSession,
) -> ResumeGenerateResponse:
    session_read, content = await generate_resume_content(
        session,
        tailoring_session_id=session_id,
        revision_request=request.revision_request,
    )
    return ResumeGenerateResponse(session=session_read, resume_content=content)


@router.post("/sessions/{session_id}/compile", response_model=ResumeCompileResponse)
def compile_resume_route(session_id: UUID, session: DbSession) -> ResumeCompileResponse:
    session_read, result = compile_tailored_resume(session, tailoring_session_id=session_id)
    return ResumeCompileResponse(session=session_read, compile_result=result)


@router.post("/sessions/{session_id}/approve-final", response_model=TailoringSessionRead)
def approve_final_route(session_id: UUID, session: DbSession) -> TailoringSessionRead:
    return approve_final_artifact(session, tailoring_session_id=session_id)


@router.get("/sessions/{session_id}/artifact/pdf", response_class=FileResponse)
def get_pdf_artifact_route(session_id: UUID, session: DbSession) -> FileResponse:
    artifact = session.exec(
        select(ResumeArtifact)
        .where(ResumeArtifact.tailoring_session_id == session_id)
        .order_by(ResumeArtifact.created_at.desc())
    ).first()
    if not artifact or not artifact.pdf_path:
        raise http_not_found("PDF artifact not found")
    pdf_path = Path(artifact.pdf_path).resolve()
    artifacts_root = settings.artifacts_dir.resolve()
    if not pdf_path.exists() or not pdf_path.is_file():
        raise http_not_found("PDF artifact file is missing")
    if artifacts_root not in pdf_path.parents:
        raise http_not_found("PDF artifact path is outside the artifacts directory")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename="tailored-resume.pdf",
    )
