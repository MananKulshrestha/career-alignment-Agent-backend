from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlmodel import Session, SQLModel, create_engine

from app.core.enums import JobStatus
from app.core.errors import BlockedWorkflowError
from app.models.tables import Job, ResumeArtifact, TailoringSession
from app.services.job_ingestion import sweep_expired_jobs
from app.services.tailoring import approve_final_artifact


def test_sweep_expired_jobs_flags_only_active_expired_jobs() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        expired = Job(
            source_hash="expired",
            title="Expired",
            company="ExampleCo",
            expires_at=now - timedelta(days=1),
        )
        future = Job(
            source_hash="future",
            title="Future",
            company="ExampleCo",
            expires_at=now + timedelta(days=1),
        )
        archived = Job(
            id=uuid4(),
            source_hash="archived",
            title="Archived",
            company="ExampleCo",
            expires_at=now - timedelta(days=1),
            status=JobStatus.ARCHIVED.value,
        )
        session.add(expired)
        session.add(future)
        session.add(archived)
        session.commit()

        assert sweep_expired_jobs(session, now=now) == 1
        session.refresh(expired)
        session.refresh(future)
        session.refresh(archived)

        assert expired.status == JobStatus.EXPIRED.value
        assert future.status == JobStatus.ACTIVE.value
        assert archived.status == JobStatus.ARCHIVED.value


def test_final_artifact_approval_requires_rendered_status() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session_id = uuid4()
        user_id = uuid4()
        job_id = uuid4()
        session.add(
            TailoringSession(
                id=session_id,
                user_id=user_id,
                job_id=job_id,
                job_spec_id=uuid4(),
                status="compile_failed",
            )
        )
        session.add(
            ResumeArtifact(
                tailoring_session_id=session_id,
                job_id=job_id,
                user_id=user_id,
                pdf_path="artifacts/session/resume.pdf",
                job_spec_version=1,
                selection_plan={"section_order": ["projects"]},
                template_plan={"placeholders": []},
                resume_content={"placeholder_values": []},
            )
        )
        session.commit()

        try:
            approve_final_artifact(session, tailoring_session_id=session_id)
        except BlockedWorkflowError as exc:
            assert "latest compile" in str(exc)
        else:
            raise AssertionError("final approval should require rendered status")
