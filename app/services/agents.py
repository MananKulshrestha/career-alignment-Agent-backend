from __future__ import annotations

import json
import os
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.schemas.job_spec import JobSpec
from app.schemas.match import MatchAnalysis
from app.schemas.profile import ProfileItemRead, UserPreference, UserProfileContextRead
from app.schemas.resume import ResumeContent, TemplatePlan
from app.schemas.selection import SelectionPlan
from app.services import fallbacks
from app.services.prompts import (
    JOB_EXTRACTION_SYSTEM_PROMPT,
    JOB_VERIFICATION_SYSTEM_PROMPT,
    MATCH_SYSTEM_PROMPT,
    PROMPT_VERSION,
    RESUME_WRITING_SYSTEM_PROMPT,
    SELECTION_SYSTEM_PROMPT,
)

T = TypeVar("T", bound=BaseModel)


class AgentGateway:
    """Pydantic AI adapter with deterministic fallbacks for keyless development."""

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION

    async def _run_structured(
        self,
        *,
        output_type: type[T],
        model_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> T:
        if settings.openai_api_key:
            os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key.get_secret_value())
        if settings.gemini_api_key:
            os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key.get_secret_value())
        try:
            from pydantic_ai import Agent
        except ImportError as exc:
            raise RuntimeError("pydantic-ai is not installed") from exc

        agent = None
        init_attempts = [
            {
                "output_type": output_type,
                "system_prompt": system_prompt,
                "retries": settings.max_model_retries,
            },
            {"output_type": output_type, "system_prompt": system_prompt},
            {
                "result_type": output_type,
                "system_prompt": system_prompt,
                "retries": settings.max_model_retries,
            },
            {"result_type": output_type, "system_prompt": system_prompt},
        ]
        for kwargs in init_attempts:
            try:
                agent = Agent(model_name, **kwargs)
                break
            except TypeError:
                continue
        if agent is None:
            raise RuntimeError("could not initialize Pydantic AI Agent with supported kwargs")
        result = await agent.run(user_prompt)
        output = getattr(result, "output", None)
        if output is None:
            output = getattr(result, "data", None)
        if output is None:
            raise RuntimeError("Pydantic AI returned no structured output")
        return output

    async def extract_job_spec(self, *, source_url: str, text: str) -> JobSpec:
        if not settings.llm_ready:
            return fallbacks.fallback_job_spec(source_url=source_url, text=text)
        prompt = _json_prompt(
            {
                "source_url": source_url,
                "job_text": text,
                "schema": JobSpec.model_json_schema(),
            }
        )
        return await self._run_structured(
            output_type=JobSpec,
            model_name=settings.cheap_model,
            system_prompt=JOB_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=prompt,
        )

    async def verify_job_spec(self, *, source_text: str, job_spec: JobSpec) -> JobSpec:
        if not settings.llm_ready:
            return job_spec
        prompt = _json_prompt(
            {
                "source_text": source_text,
                "job_spec": job_spec.model_dump(mode="json"),
                "schema": JobSpec.model_json_schema(),
            }
        )
        return await self._run_structured(
            output_type=JobSpec,
            model_name=settings.reliable_model,
            system_prompt=JOB_VERIFICATION_SYSTEM_PROMPT,
            user_prompt=prompt,
        )

    async def analyze_match(
        self,
        *,
        job_spec: JobSpec,
        profile_items: list[ProfileItemRead],
        preferences: UserPreference,
        user_context: UserProfileContextRead | None = None,
    ) -> MatchAnalysis:
        if not settings.llm_ready:
            return fallbacks.deterministic_match(
                job_spec, profile_items, preferences, user_context=user_context
            )
        prompt = _json_prompt(
            {
                "job_spec": job_spec.model_dump(mode="json"),
                "profile_items": [item.model_dump(mode="json") for item in profile_items],
                "preferences": preferences.model_dump(mode="json"),
                "user_context": user_context.model_dump(mode="json") if user_context else None,
                "schema": MatchAnalysis.model_json_schema(),
            }
        )
        return await self._run_structured(
            output_type=MatchAnalysis,
            model_name=settings.cheap_model,
            system_prompt=MATCH_SYSTEM_PROMPT,
            user_prompt=prompt,
        )

    async def create_selection_plan(
        self,
        *,
        job_spec: JobSpec,
        profile_items: list[ProfileItemRead],
        user_context: UserProfileContextRead | None = None,
        research_findings: list[dict[str, Any]] | None = None,
    ) -> SelectionPlan:
        if not settings.llm_ready:
            return fallbacks.deterministic_selection(
                job_spec, profile_items, user_context=user_context
            )
        prompt = _json_prompt(
            {
                "job_spec": job_spec.model_dump(mode="json"),
                "profile_items": [item.model_dump(mode="json") for item in profile_items],
                "user_context": user_context.model_dump(mode="json") if user_context else None,
                "research_findings": research_findings or [],
                "schema": SelectionPlan.model_json_schema(),
            }
        )
        return await self._run_structured(
            output_type=SelectionPlan,
            model_name=settings.reliable_model,
            system_prompt=SELECTION_SYSTEM_PROMPT,
            user_prompt=prompt,
        )

    async def write_resume_content(
        self,
        *,
        job_spec: JobSpec,
        template_plan: TemplatePlan,
        approved_profile_items: list[ProfileItemRead],
        user_context: UserProfileContextRead | None = None,
        revision_request: str | None = None,
    ) -> ResumeContent:
        if not settings.llm_ready:
            return fallbacks.deterministic_resume_content(
                template_plan, approved_profile_items, user_context=user_context
            )
        prompt = _json_prompt(
            {
                "job_spec": job_spec.model_dump(mode="json"),
                "template_plan": template_plan.model_dump(mode="json"),
                "approved_profile_items": [
                    item.model_dump(mode="json") for item in approved_profile_items
                ],
                "user_context": user_context.model_dump(mode="json") if user_context else None,
                "revision_request": revision_request,
                "schema": ResumeContent.model_json_schema(),
            }
        )
        return await self._run_structured(
            output_type=ResumeContent,
            model_name=settings.writing_model,
            system_prompt=RESUME_WRITING_SYSTEM_PROMPT,
            user_prompt=prompt,
        )


def _json_prompt(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


agent_gateway = AgentGateway()
