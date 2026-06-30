from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def api_health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "environment": settings.environment,
        "llm_ready": settings.llm_ready,
    }
