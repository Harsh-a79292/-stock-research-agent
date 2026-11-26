"""
api/routes/reports.py
─────────────────────
FastAPI routes for retrieving saved research reports and exporting PDFs.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.db.supabase_client import (
    get_recent_reports,
    get_report_by_id,
    report_to_agent_state,
)
from backend.services.pdf_service import generate_pdf_report

router = APIRouter(prefix="/reports", tags=["Reports"])


class ReportSummary(BaseModel):
    id: str
    ticker: str
    query: str
    intent: str | None = None
    status: str = "success"
    created_at: str | None = None


class ReportsListResponse(BaseModel):
    status: str = "success"
    count: int
    reports: list[dict[str, Any]] = Field(default_factory=list)


class ReportDetailResponse(BaseModel):
    status: str = "success"
    report: dict[str, Any]


@router.get("", response_model=ReportsListResponse, summary="List Recent Reports")
async def list_reports(limit: int = Query(default=20, ge=1, le=100)) -> ReportsListResponse:
    """Return the latest saved research reports (default 20)."""
    res = get_recent_reports(limit=limit)
    if res.get("status") == "error":
        raise HTTPException(status_code=503, detail=res.get("error", "Database unavailable."))
    reports = res.get("reports", [])
    return ReportsListResponse(status="success", count=len(reports), reports=reports)


@router.get("/{report_id}", response_model=ReportDetailResponse, summary="Get Report by ID")
async def read_report(report_id: str) -> ReportDetailResponse:
    """Return a specific saved research report by UUID."""
    res = get_report_by_id(report_id)
    if res.get("status") == "error" or not res.get("report"):
        err = res.get("error", "Report not found.")
        status_code = 404 if "not found" in err.lower() else 400 if "invalid" in err.lower() else 503
        raise HTTPException(status_code=status_code, detail=err)
    return ReportDetailResponse(status="success", report=res["report"])


@router.get("/{report_id}/pdf", summary="Download Report as PDF")
async def download_report_pdf(report_id: str) -> Response:
    """Generate and return the PDF research report for a saved report."""
    res = get_report_by_id(report_id)
    if res.get("status") == "error" or not res.get("report"):
        err = res.get("error", "Report not found.")
        status_code = 404 if "not found" in err.lower() else 400 if "invalid" in err.lower() else 503
        raise HTTPException(status_code=status_code, detail=err)

    report = res["report"]
    state = report_to_agent_state(report)
    pdf_bytes = generate_pdf_report(state)
    ticker = (report.get("ticker") or "STOCK").upper()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{ticker}_research_report.pdf"'},
    )
