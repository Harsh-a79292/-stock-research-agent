"""
tests/test_supabase_persistence.py
──────────────────────────────────
Focused unit tests for Task 6: Supabase Database Persistence.
Uses mocked Supabase client and Streamlit AppTest.
"""

from unittest.mock import MagicMock, patch
from streamlit.testing.v1 import AppTest

from backend.db.supabase_client import (
    get_recent_reports,
    get_report_by_id,
    report_to_agent_state,
    save_research_report,
)


def test_save_research_report_success():
    """Verify successful research state is serialized and inserted into research_reports."""
    mock_client = MagicMock()
    mock_exec = MagicMock()
    mock_exec.data = [{"id": "uuid-123", "ticker": "AAPL", "status": "success"}]
    mock_client.table.return_value.insert.return_value.execute.return_value = mock_exec

    state = {
        "query": "Analyze Apple",
        "ticker": "AAPL",
        "intent": "full_research",
        "analysis": "# Apple Report\nStrong fundamentals.",
        "tool_results": {
            "price": {"status": "success", "price": 185.5},
            "company_info": {"status": "success", "name": "Apple Inc."},
            "financial_summary": {"status": "success", "metrics": {"market_cap": 3e12}},
            "history": {"status": "success", "history": []},
            "news": {"status": "unavailable", "news": []},
        },
        "error": None,
    }

    with patch("backend.db.supabase_client._get_client", return_value=mock_client):
        res = save_research_report(state)

    assert res["status"] == "success"
    assert res["report"]["id"] == "uuid-123"
    mock_client.table.assert_called_once_with("research_reports")
    inserted_payload = mock_client.table.return_value.insert.call_args[0][0]
    assert inserted_payload["ticker"] == "AAPL"
    assert inserted_payload["stock_data"] == {"status": "success", "price": 185.5}
    assert inserted_payload["company_info"] == {"status": "success", "name": "Apple Inc."}


def test_save_research_report_missing_optional_fields():
    """Verify missing optional tool_results fields are safely stored as None."""
    mock_client = MagicMock()
    mock_exec = MagicMock()
    mock_exec.data = [{"id": "uuid-456", "ticker": "IBM"}]
    mock_client.table.return_value.insert.return_value.execute.return_value = mock_exec

    state = {
        "query": "IBM price",
        "ticker": "IBM",
        "intent": "price_check",
        "analysis": "IBM is trading at $235.62.",
        "tool_results": {"price": {"status": "success", "price": 235.62}},
    }

    with patch("backend.db.supabase_client._get_client", return_value=mock_client):
        res = save_research_report(state)

    assert res["status"] == "success"
    payload = mock_client.table.return_value.insert.call_args[0][0]
    assert payload["company_info"] is None
    assert payload["financial_summary"] is None
    assert payload["history"] is None
    assert payload["news"] is None


def test_save_research_report_skips_failed_runs():
    """Verify failed research runs are never saved to the database."""
    mock_client = MagicMock()

    failed_states = [
        {"query": "bad", "ticker": None, "analysis": "Error", "error": "No ticker"},
        {"query": "empty", "ticker": "AAPL", "analysis": "", "error": None},
        {"query": "err", "ticker": "AAPL", "analysis": "Report", "error": "API error"},
        {
            "query": "all tools failed",
            "ticker": "AAPL",
            "analysis": "Fallback",
            "error": None,
            "tool_results": {"price": {"status": "error", "error": "Rate limit"}},
        },
    ]

    with patch("backend.db.supabase_client._get_client", return_value=mock_client):
        for state in failed_states:
            res = save_research_report(state)
            assert res["status"] == "skipped"

    mock_client.table.assert_not_called()


def test_get_recent_reports_success():
    """Verify recent reports retrieval orders by created_at DESC with limit."""
    mock_client = MagicMock()
    mock_exec = MagicMock()
    mock_exec.data = [
        {"id": "1", "ticker": "AAPL", "query": "AAPL price", "created_at": "2026-11-25T10:00:00Z"},
        {"id": "2", "ticker": "IBM", "query": "IBM info", "created_at": "2026-11-25T09:00:00Z"},
    ]
    (
        mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value
    ) = mock_exec

    with patch("backend.db.supabase_client._get_client", return_value=mock_client):
        res = get_recent_reports(limit=20)

    assert res["status"] == "success"
    assert len(res["reports"]) == 2
    assert res["reports"][0]["ticker"] == "AAPL"


def test_get_report_by_id_success_and_not_found():
    """Verify fetching a report by UUID returns data or clean not-found error."""
    mock_client = MagicMock()
    mock_exec = MagicMock()
    mock_exec.data = [{"id": "uuid-1", "ticker": "MSFT", "analysis": "Microsoft report"}]
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_exec

    with patch("backend.db.supabase_client._get_client", return_value=mock_client):
        res = get_report_by_id("uuid-1")
        assert res["status"] == "success"
        assert res["report"]["ticker"] == "MSFT"

        # Empty data -> not found
        mock_exec.data = []
        res_missing = get_report_by_id("uuid-missing")
        assert res_missing["status"] == "error"
        assert res_missing["report"] is None


def test_supabase_database_error_handling():
    """Verify database exceptions are caught gracefully without exposing credentials."""
    mock_client = MagicMock()
    mock_client.table.side_effect = RuntimeError("Connection refused")

    state = {
        "query": "IBM",
        "ticker": "IBM",
        "analysis": "IBM analysis",
        "tool_results": {"price": {"status": "success", "price": 235.0}},
    }

    with patch("backend.db.supabase_client._get_client", return_value=mock_client):
        save_res = save_research_report(state)
        assert save_res["status"] == "error"
        assert "Database error" in save_res["error"]

        recent_res = get_recent_reports()
        assert recent_res["status"] == "error"
        assert recent_res["reports"] == []

        by_id_res = get_report_by_id("uuid-1")
        assert by_id_res["status"] == "error"
        assert by_id_res["report"] is None


def test_streamlit_history_display_and_load():
    """Verify Streamlit sidebar displays Research History and loads a selected report."""
    recent_mock = {
        "status": "success",
        "reports": [
            {
                "id": "rep-101",
                "ticker": "NVDA",
                "query": "Analyze NVDA",
                "intent": "full_research",
                "status": "success",
                "created_at": "2026-11-25T12:00:00Z",
            }
        ],
    }
    full_report_mock = {
        "status": "success",
        "report": {
            "id": "rep-101",
            "ticker": "NVDA",
            "query": "Analyze NVDA",
            "intent": "full_research",
            "status": "success",
            "analysis": "# NVIDIA Saved Analysis\nStrong GPU demand.",
            "stock_data": {"status": "success", "price": 140.0, "previous_close": 135.0, "change": 5.0, "change_percent": 3.7},
            "company_info": {"status": "success", "name": "NVIDIA Corp", "sector": "Technology"},
            "financial_summary": None,
            "history": None,
            "news": None,
            "created_at": "2026-11-25T12:00:00Z",
        },
    }

    with patch("backend.db.supabase_client.get_recent_reports", return_value=recent_mock), \
         patch("backend.db.supabase_client.get_report_by_id", return_value=full_report_mock) as mock_get_id:
        at = AppTest.from_file("frontend/app.py", default_timeout=15)
        at.run()
        assert not at.exception, f"Startup exception: {at.exception}"

        # Selectbox should be rendered in sidebar with NVDA report
        sb = at.sidebar.selectbox(key="saved_report_select")
        assert len(sb.options) == 1
        assert "NVDA" in sb.options[0]

        # Click Load Saved Report
        at.sidebar.button(key="load_saved_report_btn").click().run()
        assert not at.exception, f"Load exception: {at.exception}"
        mock_get_id.assert_called_once_with("rep-101")
        assert at.session_state["latest_result"]["ticker"] == "NVDA"
        assert "NVIDIA Saved Analysis" in at.session_state["latest_result"]["analysis"]
