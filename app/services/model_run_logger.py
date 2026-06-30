from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.models.tables import ModelRun
from app.services.prompts import PROMPT_VERSION


def record_model_run(
    session: Session,
    *,
    stage: str,
    model_name: str,
    user_id: UUID | None = None,
    job_id: UUID | None = None,
    tailoring_session_id: UUID | None = None,
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> None:
    session.add(
        ModelRun(
            user_id=user_id,
            job_id=job_id,
            tailoring_session_id=tailoring_session_id,
            stage=stage,
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            input_summary=input_summary or {},
            output_summary=output_summary or {},
            success=success,
            error_message=error_message,
        )
    )
