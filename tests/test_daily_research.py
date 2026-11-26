"""
tests/test_daily_research.py
────────────────────────────
Focused unit tests for Task 8: Automated Daily Stock Research & Email Delivery.
All external APIs (LangGraph agent, Supabase, PDF, Gmail) are mocked.
"""

from unittest.mock import patch

from backend.scripts.daily_research import parse_tickers, run_daily_research


def test_parse_tickers_deduplicates_and_normalizes():
    assert parse_tickers(" aapl, msft ,AAPL, nvda , ") == ["AAPL", "MSFT", "NVDA"]
    assert parse_tickers("") == []
    assert parse_tickers(None) == []


def test_daily_research_atomic_claim_blocks_concurrent_duplicate():
    claimed_keys: set[tuple[str, str, str]] = set()

    def fake_claim(run_date: str, ticker: str, recipient: str, **_kwargs) -> bool:
        key = (run_date, ticker.upper(), recipient.lower())
        if key in claimed_keys:
            return False
        claimed_keys.add(key)
        return True

    mock_state = {
        "query": "Comprehensive daily stock research report for AAPL",
        "ticker": "AAPL",
        "intent": "full_research",
        "tool_results": {"price": {"price": 210.0}},
        "analysis": "Apple shows strong fundamentals.",
        "error": None,
    }

    with (
        patch("backend.scripts.daily_research.claim_daily_email_delivery", side_effect=fake_claim),
        patch("backend.scripts.daily_research.update_daily_email_delivery"),
        patch("backend.scripts.daily_research.agent_graph") as mock_graph,
        patch("backend.scripts.daily_research.save_research_report") as mock_save,
        patch("backend.scripts.daily_research.generate_pdf_report") as mock_pdf,
        patch("backend.scripts.daily_research.send_research_email") as mock_email,
    ):
        mock_graph.invoke.return_value = mock_state
        mock_save.return_value = {"status": "success", "report": {"id": "rep-123"}}
        mock_pdf.return_value = b"%PDF-1.4 mock"
        mock_email.return_value = {"status": "success", "message_id": "msg-001"}

        res1 = run_daily_research(tickers=["AAPL"], recipient="investor@example.com")
        assert len(res1["processed"]) == 1
        assert res1["processed"][0]["ticker"] == "AAPL"
        assert res1["processed"][0]["message_id"] == "msg-001"
        assert res1["failed"] == []

        # Second concurrent/duplicate run on the same UTC date is blocked before sending
        res2 = run_daily_research(tickers=["AAPL"], recipient="investor@example.com")
        assert res2["processed"] == []
        assert len(res2["skipped"]) == 1
        assert res2["skipped"][0]["reason"] == "already_sent_today"
        assert mock_email.call_count == 1


def test_daily_research_continues_on_api_failure():
    def side_effect(payload):
        if "BAD" in payload["query"]:
            raise RuntimeError("Alpha Vantage timeout")
        return {
            "query": payload["query"],
            "ticker": "MSFT",
            "analysis": "Microsoft cloud growth remains strong.",
            "error": None,
        }

    with (
        patch("backend.scripts.daily_research.claim_daily_email_delivery", return_value=True),
        patch("backend.scripts.daily_research.update_daily_email_delivery"),
        patch("backend.scripts.daily_research.agent_graph") as mock_graph,
        patch("backend.scripts.daily_research.save_research_report") as mock_save,
        patch("backend.scripts.daily_research.generate_pdf_report") as mock_pdf,
        patch("backend.scripts.daily_research.send_research_email") as mock_email,
    ):
        mock_graph.invoke.side_effect = side_effect
        mock_save.return_value = {"status": "success", "report": {"id": "rep-456"}}
        mock_pdf.return_value = b"%PDF-1.4 mock"
        mock_email.return_value = {"status": "success", "message_id": "msg-002"}

        res = run_daily_research(tickers=["BAD", "MSFT"], recipient="investor@example.com")
        assert len(res["failed"]) == 1
        assert res["failed"][0]["ticker"] == "BAD"
        assert len(res["processed"]) == 1
        assert res["processed"][0]["ticker"] == "MSFT"


def test_daily_research_invalid_config():
    res_no_tickers = run_daily_research(tickers=[], recipient="investor@example.com")
    assert res_no_tickers["error"] == "No tickers configured."

    res_bad_email = run_daily_research(tickers=["AAPL"], recipient="not-an-email")
    assert "Invalid email" in res_bad_email["error"]
