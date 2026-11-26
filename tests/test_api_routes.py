"""
tests/test_api_routes.py
────────────────────────
Focused tests for Task 7: FastAPI Backend API Integration.
Tests /agent/run, /reports, /reports/{id}, /reports/{id}/pdf, /health,
and invalid request handling.
"""

from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify GET /health returns 200 OK."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_post_agent_run_success_and_single_save():
    """Verify POST /agent/run executes agent_graph and saves once to Supabase."""
    mock_state = {
        "query": "What is IBM stock price?",
        "ticker": "IBM",
        "intent": "price_check",
        "tool_results": {"price": {"status": "success", "price": 235.62}},
        "analysis": "# IBM Report\nTrading at $235.62.",
        "error": None,
    }
    mock_save = {"status": "success", "report": {"id": "uuid-ibm-1"}}

    with patch("backend.api.routes.agent.agent_graph") as mock_graph, \
         patch("backend.api.routes.agent.save_research_report", return_value=mock_save) as mock_save_fn:
        mock_graph.invoke.return_value = mock_state
        resp = client.post("/agent/run", json={"query": "  What is IBM stock price?  "})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "IBM"
    assert data["intent"] == "price_check"
    assert data["saved_report_id"] == "uuid-ibm-1"
    assert data["save_status"] == "success"
    mock_graph.invoke.assert_called_once_with({"query": "What is IBM stock price?"})
    mock_save_fn.assert_called_once_with(mock_state)


def test_post_agent_run_invalid_blank_query():
    """Verify blank or missing query returns 422 validation error."""
    resp_blank = client.post("/agent/run", json={"query": "   "})
    assert resp_blank.status_code == 422

    resp_missing = client.post("/agent/run", json={})
    assert resp_missing.status_code == 422


def test_get_reports_list():
    """Verify GET /reports returns recent saved reports."""
    mock_reports = {
        "status": "success",
        "reports": [
            {"id": "1", "ticker": "AAPL", "query": "AAPL", "created_at": "2026-11-25T10:00:00Z"},
            {"id": "2", "ticker": "IBM", "query": "IBM", "created_at": "2026-11-25T09:00:00Z"},
        ],
    }

    with patch("backend.api.routes.reports.get_recent_reports", return_value=mock_reports) as mock_get:
        resp = client.get("/reports")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["count"] == 2
    assert data["reports"][0]["ticker"] == "AAPL"
    mock_get.assert_called_once_with(limit=20)


def test_get_report_by_id_success_and_not_found():
    """Verify GET /reports/{id} returns report or 404 when missing."""
    mock_found = {
        "status": "success",
        "report": {"id": "rep-1", "ticker": "MSFT", "analysis": "Microsoft report"},
    }
    with patch("backend.api.routes.reports.get_report_by_id", return_value=mock_found):
        resp = client.get("/reports/rep-1")
    assert resp.status_code == 200
    assert resp.json()["report"]["ticker"] == "MSFT"

    mock_missing = {"status": "error", "report": None, "error": "Report not found: bad-id"}
    with patch("backend.api.routes.reports.get_report_by_id", return_value=mock_missing):
        resp_404 = client.get("/reports/bad-id")
    assert resp_404.status_code == 404


def test_get_report_pdf_success_and_not_found():
    """Verify GET /reports/{id}/pdf returns valid PDF bytes and 404 if missing."""
    mock_found = {
        "status": "success",
        "report": {
            "id": "rep-1",
            "ticker": "IBM",
            "query": "Analyze IBM",
            "intent": "price_check",
            "analysis": "# IBM Analysis\nSolid performance.",
            "stock_data": {"status": "success", "price": 235.62, "previous_close": 233.0, "change": 2.62, "change_percent": 1.12},
            "company_info": None,
            "financial_summary": None,
            "history": None,
            "news": None,
        },
    }
    with patch("backend.api.routes.reports.get_report_by_id", return_value=mock_found):
        resp = client.get("/reports/rep-1/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "IBM_research_report.pdf" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF-")

    mock_missing = {"status": "error", "report": None, "error": "Report not found: bad-id"}
    with patch("backend.api.routes.reports.get_report_by_id", return_value=mock_missing):
        resp_404 = client.get("/reports/bad-id/pdf")
    assert resp_404.status_code == 404
