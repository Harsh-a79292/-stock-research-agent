"""
main.py
───────
FastAPI application entry point.
Run with:  uvicorn backend.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import agent, health, reports
from backend.core.config import settings

LOCAL_DEV_ORIGINS = [
    "http://localhost:8501",
    "http://127.0.0.1:8501",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def get_allowed_origins(cors_origins: str | None = None, app_env: str | None = None) -> list[str]:
    """
    Build the allowed CORS origin list.
    Preserves local development origins by default and merges comma-separated
    production origins from CORS_ORIGINS.
    """
    raw = settings.cors_origins if cors_origins is None else cors_origins
    env = (settings.app_env if app_env is None else app_env).strip().lower()

    configured = [
        o.strip().rstrip("/")
        for o in (raw or "").split(",")
        if o.strip()
    ]

    if env == "production" and configured:
        return list(dict.fromkeys(configured))

    return list(dict.fromkeys([*LOCAL_DEV_ORIGINS, *configured]))


# ── App Initialisation ────────────────────────────────────────────────────────
app = FastAPI(
    title="Stock Research Agent API",
    description="AI-powered stock research and automation backend.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(agent.router)
app.include_router(reports.router)

# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root():
    """API root — points to the docs."""
    return {
        "message": "Welcome to the Stock Research Agent API 🚀",
        "docs": "/docs",
        "health": "/health",
    }
