from fastapi import APIRouter

from app.api.routes import health, jobs, profiles, tailoring

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
api_router.include_router(tailoring.router, prefix="/tailoring", tags=["tailoring"])
