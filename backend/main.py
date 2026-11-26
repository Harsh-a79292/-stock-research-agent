"""
main.py
───────
FastAPI application entry point.
Run with:  uvicorn backend.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import agent, health, reports

# ── App Initialisation ────────────────────────────────────────────────────────
app = FastAPI(
    title="Stock Research Agent API",
    description="AI-powered stock research and automation backend.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS (Local Development Origins Only) ─────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
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
