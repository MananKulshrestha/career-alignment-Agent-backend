from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.core.errors import http_not_found
from app.models.tables import Job
from app.schemas.api import (
    JobIngestRequest,
    JobIngestResponse,
    JobListItem,
    JobRead,
    MatchRequest,
    UserJobMatchRead,
)
from app.schemas.job_spec import JobSpec
from app.services.job_ingestion import (
    get_latest_job_spec_record,
    get_user_job_match,
    ingest_job,
    list_jobs,
    match_job_for_user,
    sweep_expired_jobs,
)

router = APIRouter()


@router.post("/ingest", response_model=JobIngestResponse)
async def ingest_job_route(request: JobIngestRequest, session: DbSession) -> JobIngestResponse:
    return await ingest_job(session, request)


@router.get("", response_model=list[JobListItem])
def list_jobs_route(
    session: DbSession,
    user_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[JobListItem]:
    return list_jobs(session, user_id=user_id, limit=limit)


@router.get("/{job_id}", response_model=JobIngestResponse)
def get_job_route(
    job_id: UUID,
    session: DbSession,
    user_id: UUID | None = None,
) -> JobIngestResponse:
    job = session.get(Job, job_id)
    if not job:
        raise http_not_found("job not found")
    spec = get_latest_job_spec_record(session, job_id)
    return JobIngestResponse(
        job=JobRead(
            id=job.id,
            title=job.title,
            company=job.company,
            canonical_url=job.canonical_url,
            source_hash=job.source_hash,
            status=job.status,
        ),
        job_spec=JobSpec.model_validate(spec.structured_json),
        reused_existing_job=True,
        match=get_user_job_match(session, user_id=user_id, job_id=job_id),
    )


@router.post("/{job_id}/match", response_model=UserJobMatchRead)
async def match_job_route(
    job_id: UUID,
    request: MatchRequest,
    session: DbSession,
) -> UserJobMatchRead:
    return await match_job_for_user(session, job_id=job_id, request=request)


@router.post("/maintenance/sweep-expired")
def sweep_expired_jobs_route(session: DbSession) -> dict[str, int]:
    return {"expired_jobs": sweep_expired_jobs(session)}
