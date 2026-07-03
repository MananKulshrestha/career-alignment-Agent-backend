from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlmodel import Session, select

from app.core.config import settings
from app.core.enums import ExtractionRisk, JobStatus, TailoringStatus
from app.core.errors import BlockedWorkflowError
from app.models.tables import Job, JobSpecRecord, UserJobMatch, utc_now
from app.schemas.api import (
    JobIngestRequest,
    JobIngestResponse,
    JobListItem,
    JobRead,
    MatchRequest,
    UserJobMatchRead,
)
from app.schemas.job_spec import JobSpec
from app.schemas.profile import UserPreference
from app.services.agents import agent_gateway
from app.services.model_run_logger import record_model_run
from app.services.profile_service import get_profile
from app.services.scraper import fetch_first_job_for_query, fetch_job_text
from app.services.url_normalizer import canonicalize_url, sha256_text
from app.services.validation import validate_job_spec_handoff

logger = logging.getLogger(__name__)


async def ingest_job(session: Session, request: JobIngestRequest) -> JobIngestResponse:
    source_url, source_text, canonical_url, url_hash, source_hash = await _resolve_submission(
        request
    )

    existing_job = session.exec(select(Job).where(Job.source_hash == source_hash)).first()
    if existing_job:
        latest_spec = get_latest_job_spec_record(session, existing_job.id)
        match = await match_job_for_user(
            session,
            job_id=existing_job.id,
            request=MatchRequest(
                user_id=request.user_id,
                preferences=UserPreference(match_threshold=request.match_threshold),
            ),
        )
        return JobIngestResponse(
            job=_job_read(existing_job),
            job_spec=JobSpec.model_validate(latest_spec.structured_json),
            reused_existing_job=True,
            match=match,
        )

    job_spec = await agent_gateway.extract_job_spec(source_url=source_url, text=source_text)
    if job_spec.extraction.risk in {ExtractionRisk.MEDIUM, ExtractionRisk.HIGH}:
        logger.info(
            "Job extraction resulted in %s risk. Triggering verification review loop.",
            job_spec.extraction.risk.value,
        )
        job_spec = await agent_gateway.verify_job_spec(source_text=source_text, job_spec=job_spec)
    validate_job_spec_handoff(job_spec)

    job = Job(
        canonical_url=canonical_url,
        url_hash=url_hash,
        source_hash=source_hash,
        title=job_spec.title,
        company=job_spec.company,
        location=job_spec.location,
        remote_policy=job_spec.remote_policy.value,
        salary_min=job_spec.salary.min,
        salary_max=job_spec.salary.max,
        deadline=job_spec.application_deadline,
        expires_at=_compute_expires_at(job_spec),
        status=JobStatus.ACTIVE.value,
    )
    session.add(job)
    session.flush()

    spec_record = JobSpecRecord(
        job_id=job.id,
        version=1,
        schema_version=job_spec.schema_version,
        structured_json=job_spec.model_dump(mode="json"),
        parsed_markdown=job_spec.parsed_markdown,
        raw_text_fallback=job_spec.raw_text_fallback,
        extraction_risk=job_spec.extraction.risk.value,
        extraction_model=job_spec.extraction.model,
        verification_model=settings.reliable_model
        if job_spec.extraction.risk != ExtractionRisk.LOW
        else None,
        source_url=job_spec.source_url,
        parsed_at=job_spec.extraction.parsed_at,
        verified_at=utc_now() if job_spec.extraction.verified else None,
    )
    session.add(spec_record)
    record_model_run(
        session,
        stage="job_extraction",
        model_name=job_spec.extraction.model,
        user_id=request.user_id,
        job_id=job.id,
        input_summary={"source_url": source_url, "chars": len(source_text)},
        output_summary={"risk": job_spec.extraction.risk.value, "title": job_spec.title},
    )
    session.commit()
    session.refresh(job)

    match = await match_job_for_user(
        session,
        job_id=job.id,
        request=MatchRequest(
            user_id=request.user_id,
            preferences=UserPreference(match_threshold=request.match_threshold),
        ),
    )
    return JobIngestResponse(
        job=_job_read(job),
        job_spec=job_spec,
        reused_existing_job=False,
        match=match,
    )


async def match_job_for_user(
    session: Session,
    *,
    job_id: UUID,
    request: MatchRequest,
) -> UserJobMatchRead:
    job = session.get(Job, job_id)
    if not job:
        raise BlockedWorkflowError("job not found")
    spec_record = get_latest_job_spec_record(session, job_id)
    job_spec = JobSpec.model_validate(spec_record.structured_json)
    profile = get_profile(session, user_id=request.user_id, preferences=request.preferences)
    analysis = await agent_gateway.analyze_match(
        job_spec=job_spec,
        profile_items=profile.items,
        preferences=request.preferences,
        user_context=profile.context,
    )

    existing = session.exec(
        select(UserJobMatch).where(
            UserJobMatch.user_id == request.user_id,
            UserJobMatch.job_id == job_id,
        )
    ).first()
    record = existing or UserJobMatch(user_id=request.user_id, job_id=job_id)
    record.match_score = analysis.match_score
    record.match_verdict = analysis.match_verdict.value
    record.preference_failures = analysis.preference_failures
    record.missing_requirements = [
        item.model_dump(mode="json") for item in analysis.missing_requirements
    ]
    record.adjacent_evidence = [item.model_dump(mode="json") for item in analysis.adjacent_evidence]
    record.short_explanation = analysis.short_explanation
    if not existing:
        record.tailoring_status = TailoringStatus.NOT_STARTED.value
    record.updated_at = utc_now()
    if not existing:
        session.add(record)
    record_model_run(
        session,
        stage="match_analysis",
        model_name=settings.cheap_model if settings.llm_ready else "deterministic-fallback",
        user_id=request.user_id,
        job_id=job_id,
        input_summary={"profile_item_count": len(profile.items)},
        output_summary={"score": analysis.match_score, "verdict": analysis.match_verdict.value},
    )
    session.commit()
    session.refresh(record)
    return _match_read(record)


def get_latest_job_spec_record(session: Session, job_id: UUID) -> JobSpecRecord:
    record = session.exec(
        select(JobSpecRecord)
        .where(JobSpecRecord.job_id == job_id)
        .order_by(JobSpecRecord.version.desc())
    ).first()
    if not record:
        raise BlockedWorkflowError("job has no stored job_spec")
    return record


def get_user_job_match(
    session: Session, *, user_id: UUID | None, job_id: UUID
) -> UserJobMatchRead | None:
    if user_id is None:
        return None
    record = session.exec(
        select(UserJobMatch).where(
            UserJobMatch.user_id == user_id,
            UserJobMatch.job_id == job_id,
        )
    ).first()
    return _match_read(record) if record else None


def list_jobs(
    session: Session, *, user_id: UUID | None = None, limit: int = 50
) -> list[JobListItem]:
    jobs = session.exec(select(Job).order_by(Job.updated_at.desc()).limit(limit)).all()
    if user_id is None:
        return [JobListItem(job=_job_read(job), match=None) for job in jobs]

    matches = session.exec(
        select(UserJobMatch).where(
            UserJobMatch.user_id == user_id,
            UserJobMatch.job_id.in_([job.id for job in jobs]),
        )
    ).all()
    matches_by_job_id = {match.job_id: _match_read(match) for match in matches}
    return [JobListItem(job=_job_read(job), match=matches_by_job_id.get(job.id)) for job in jobs]


async def _resolve_submission(
    request: JobIngestRequest,
) -> tuple[str, str, str | None, str | None, str]:
    if request.kind == "url":
        if request.url is None:
            raise BlockedWorkflowError("url submission is missing url")
        canonical_url = canonicalize_url(request.url)
        source_text = await fetch_job_text(canonical_url)
        url_hash = sha256_text(canonical_url)
        source_hash = sha256_text(canonical_url)
        return canonical_url, source_text, canonical_url, url_hash, source_hash
    if request.kind == "query":
        if request.query is None:
            raise BlockedWorkflowError("query submission is missing query")
        source_url, source_text = await fetch_first_job_for_query(request.query)
        canonical_url = canonicalize_url(source_url)
        url_hash = sha256_text(canonical_url)
        source_hash = sha256_text(canonical_url)
        return canonical_url, source_text, canonical_url, url_hash, source_hash
    if request.pasted_text is None:
        raise BlockedWorkflowError("text submission is missing pasted_text")
    source_text = request.pasted_text[: settings.max_job_text_chars]
    source_url = f"manual://{sha256_text(source_text)[:16]}"
    source_hash = sha256_text(source_text)
    return source_url, source_text, None, None, source_hash


def _compute_expires_at(job_spec: JobSpec) -> datetime:
    if job_spec.application_deadline:
        try:
            return datetime.fromisoformat(job_spec.application_deadline).astimezone(timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc) + timedelta(days=30)
    return datetime.now(timezone.utc) + timedelta(days=30)


def _job_read(job: Job) -> JobRead:
    return JobRead(
        id=job.id,
        title=job.title,
        company=job.company,
        canonical_url=job.canonical_url,
        source_hash=job.source_hash,
        status=job.status,
    )


def _match_read(record: UserJobMatch) -> UserJobMatchRead:
    return UserJobMatchRead(
        id=record.id,
        user_id=record.user_id,
        job_id=record.job_id,
        match_score=record.match_score,
        match_verdict=record.match_verdict,
        preference_failures=record.preference_failures,
        missing_requirements=record.missing_requirements,
        adjacent_evidence=record.adjacent_evidence,
        short_explanation=record.short_explanation,
        saved_status=record.saved_status,
        application_status=record.application_status,
        tailoring_status=record.tailoring_status,
    )


def sweep_expired_jobs(session: Session, *, now: datetime | None = None) -> int:
    reference_time = now or datetime.now(timezone.utc)
    expired_jobs = session.exec(
        select(Job).where(
            Job.status == JobStatus.ACTIVE.value,
            Job.expires_at != None,  # noqa: E711
            Job.expires_at <= reference_time,
        )
    ).all()
    for job in expired_jobs:
        job.status = JobStatus.EXPIRED.value
        job.updated_at = utc_now()
    session.commit()
    return len(expired_jobs)
