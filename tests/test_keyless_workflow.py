from uuid import uuid4

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.schemas.api import JobIngestRequest, SubmissionKind, TailoringSessionCreate
from app.schemas.profile import ProfileItemCreate, ProfileItemKind, ProfileItemPayload
from app.schemas.selection import SelectionApproval
from app.services.job_ingestion import ingest_job, list_jobs
from app.services.profile_service import add_profile_item
from app.services.tailoring import (
    approve_selection,
    create_tailoring_session,
    generate_resume_content,
)


@pytest.mark.asyncio
async def test_keyless_text_to_resume_content_workflow() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user_id = uuid4()

    with Session(engine) as session:
        add_profile_item(
            session,
            user_id=user_id,
            request=ProfileItemCreate(
                kind=ProfileItemKind.PROJECT,
                source_item_id="project_backend_tracker",
                payload=ProfileItemPayload(
                    title="Backend Job Tracker",
                    description=(
                        "Built a FastAPI and PostgreSQL job tracker with reliable "
                        "REST endpoints and Docker-based deployment."
                    ),
                    skills=["Python", "FastAPI", "PostgreSQL", "Docker", "REST"],
                ),
            ),
        )

        ingest_response = await ingest_job(
            session,
            JobIngestRequest(
                user_id=user_id,
                kind=SubmissionKind.TEXT,
                pasted_text=(
                    "Backend Engineer at ExampleCo\n"
                    "Company: ExampleCo\n"
                    "We need Python, FastAPI, PostgreSQL, REST, and Docker. "
                    "You will build reliable APIs for application workflows."
                ),
            ),
        )

        assert ingest_response.match is not None
        assert ingest_response.match.match_score > 0
        assert ingest_response.match.saved_status == "new"
        assert ingest_response.match.application_status == "not_started"
        assert ingest_response.match.tailoring_status == "not_started"

        session_read = await create_tailoring_session(
            session,
            user_id=TailoringSessionCreate(
                user_id=user_id,
                job_id=ingest_response.job.id,
            ).user_id,
            job_id=ingest_response.job.id,
        )
        assert session_read.selection_plan is not None
        listed_jobs = list_jobs(session, user_id=user_id)
        assert len(listed_jobs) == 1
        assert listed_jobs[0].job.id == ingest_response.job.id
        assert listed_jobs[0].match is not None
        assert listed_jobs[0].match.tailoring_status == "selection_draft"

        approved = approve_selection(
            session,
            tailoring_session_id=session_read.id,
            approval=SelectionApproval(
                selection_plan=session_read.selection_plan,
                approved_by_user=True,
            ),
        )
        assert approved.template_plan is not None

        generated, content = await generate_resume_content(
            session,
            tailoring_session_id=session_read.id,
        )
        assert generated.resume_content is not None
        assert content.placeholder_values
