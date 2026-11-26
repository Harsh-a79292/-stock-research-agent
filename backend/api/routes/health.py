"""
api/routes/health.py
─────────────────────
Health-check endpoint.
GET /health  →  confirms the API is running and returns basic metadata.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    environment: str
    timestamp: str
    version: str


@router.get("/health", response_model=HealthResponse, summary="Health Check")
async def health_check() -> HealthResponse:
    """
    Returns a 200 OK response with server metadata.
    Use this endpoint to verify the API is reachable and running.
    """
    from backend.core.config import settings

    return HealthResponse(
        status="ok",
        environment=settings.app_env,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="0.1.0",
    )
