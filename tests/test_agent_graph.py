"""
tests/test_agent_graph.py
─────────────────────────
Unit tests for the Phase 2 LangGraph agent and Gemini service.
Tests natural language parsing, selective tool routing, deterministic fallbacks,
and error handling.
"""

from unittest.mock import MagicMock, patch
import pytest

from backend.agent.graph import agent_graph
from backend.services.gemini_service import (
    fallback_parse_query,
    generate_deterministic_report,
    parse_query_with_gemini,
)


# ── Query Parsing Tests ───────────────────────────────────────────────────────

def test_parse_query_with_gemini_success():
    """Test parse_query_with_gemini when Gemini returns valid JSON."""
    mock_response = MagicMock()
    mock_response.text = '{"ticker": "NVDA", "intent": "price_check"}'

    with patch("backend.services.gemini_service.get_gemini_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        res = parse_query_with_gemini("What is Nvidia trading at today?")
        assert res["ticker"] == "NVDA"
        assert res["intent"] == "price_check"


def test_parse_query_with_gemini_markdown_fence():
    """Test parse_query_with_gemini strips markdown code fences from LLM response."""
    mock_response = MagicMock()
    mock_response.text = '```json\n{"ticker": "MSFT", "intent": "fundamentals"}\n```'

    with patch("backend.services.gemini_service.get_gemini_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        res = parse_query_with_gemini("Tell me Microsoft's P/E ratio")
        assert res["ticker"] == "MSFT"
        assert res["intent"] == "fundamentals"


def test_fallback_parse_query_company_mappings():
    """Test fallback_parse_query maps known company names to tickers."""
    test_cases = [
        ("What is Apple's current stock price?", "AAPL", "price_check"),
        ("Show me Microsoft valuation and P/E ratio", "MSFT", "fundamentals"),
        ("Deep dive research report on Tesla", "TSLA", "full_research"),
        ("Analyze Google", "GOOGL", "full_research"),
        ("IBM share price", "IBM", "price_check"),
    ]
    for query, expected_ticker, expected_intent in test_cases:
        res = fallback_parse_query(query)
        assert res["ticker"] == expected_ticker
        assert res["intent"] == expected_intent


def test_fallback_parse_query_cashtags_and_tickers():
    """Test fallback_parse_query recognizes $TICKER and uppercase tickers."""
    assert fallback_parse_query("What is $AMD trading at?")["ticker"] == "AMD"
    assert fallback_parse_query("Analyze NVDA")["ticker"] == "NVDA"
    assert fallback_parse_query("Price of CRM")["ticker"] == "CRM"


def test_fallback_parse_query_no_ticker():
    """Test fallback_parse_query returns None for queries without stocks."""
    assert fallback_parse_query("Hello, how are you?")["ticker"] is None
    assert fallback_parse_query("What is the weather in New York?")["ticker"] is None
    assert fallback_parse_query("")["ticker"] is None


# ── Deterministic Report Tests ────────────────────────────────────────────────

def test_generate_deterministic_report_formatting():
    """Test generate_deterministic_report produces structured markdown."""
    tool_results = {
        "price": {
            "status": "success",
            "price": 185.50,
            "previous_close": 180.00,
            "change": 5.50,
            "change_percent": 3.06,
            "timestamp": "2026-03-30T10:00:00Z",
        },
        "company_info": {
            "status": "success",
            "name": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "country": "USA",
            "fifty_two_week_high": 199.62,
            "fifty_two_week_low": 164.08,
        },
        "financial_summary": {
            "status": "success",
            "metrics": {
                "market_cap": 3000000000000,
                "trailing_pe": 30.5,
                "forward_pe": 28.0,
                "profit_margins": 0.25,
            },
        },
    }

    report = generate_deterministic_report(
        query="Analyze Apple",
        ticker="AAPL",
        intent="fundamentals",
        tool_results=tool_results,
    )

    assert "# Stock Research Report: AAPL" in report
    assert "Current Price**: $185.50" in report
    assert "Apple Inc." in report
    assert "Technology" in report
    assert "Market Cap**: $3,000,000,000,000" in report
    assert "Trailing P/E**: 30.5" in report


# ── LangGraph Agent Integration & Routing Tests ───────────────────────────────

def test_graph_invalid_query_conditional_routing():
    """Test that queries without a valid ticker route to handle_error without calling tools."""
    with patch("backend.services.gemini_service.get_gemini_client", return_value=None):
        result = agent_graph.invoke({"query": "What is the capital of France?"})

        assert result["error"] is not None
        assert result["ticker"] is None
        assert "Stock Research Error" in result["analysis"]
        assert "tool_results" not in result or not result["tool_results"]


def test_graph_empty_query():
    """Test that empty queries are rejected cleanly."""
    result = agent_graph.invoke({"query": "   "})
    assert result["error"] is not None
    assert result["ticker"] is None
    assert "Query cannot be empty" in result["analysis"]


def test_graph_price_check_selective_tool_execution():
    """Test price_check intent only invokes get_stock_price, saving API quota."""
    mock_price = {
        "status": "success",
        "ticker": "AAPL",
        "price": 175.20,
        "previous_close": 174.00,
        "change": 1.20,
        "change_percent": 0.69,
        "timestamp": "2026-03-30T10:00:00Z",
    }

    with patch("backend.services.gemini_service.get_gemini_client", return_value=None), \
         patch("backend.agent.graph.get_stock_price") as mock_price_tool, \
         patch("backend.agent.graph.get_company_info") as mock_info_tool, \
         patch("backend.agent.graph.get_stock_history") as mock_hist_tool:

        mock_price_tool.invoke.return_value = mock_price

        result = agent_graph.invoke({"query": "What is Apple's current stock price?"})

        assert result["ticker"] == "AAPL"
        assert result["intent"] == "price_check"
        mock_price_tool.invoke.assert_called_once_with({"ticker": "AAPL"})
        mock_info_tool.invoke.assert_not_called()
        mock_hist_tool.invoke.assert_not_called()
        assert "Current Price**: $175.20" in result["analysis"]


def test_graph_fundamentals_selective_tool_execution():
    """Test fundamentals intent calls price, company info, and financial summary."""
    mock_price = {"status": "success", "price": 180.0, "previous_close": 180.0, "change": 0.0, "change_percent": 0.0}
    mock_info = {"status": "success", "name": "IBM Corp", "sector": "Tech", "industry": "IT", "country": "USA"}
    mock_fin = {"status": "success", "metrics": {"market_cap": 200000000000, "trailing_pe": 22.5}}

    with patch("backend.services.gemini_service.get_gemini_client", return_value=None), \
         patch("backend.agent.graph.get_stock_price") as mock_price_tool, \
         patch("backend.agent.graph.get_company_info") as mock_info_tool, \
         patch("backend.agent.graph.get_financial_summary") as mock_fin_tool, \
         patch("backend.agent.graph.get_stock_history") as mock_hist_tool:

        mock_price_tool.invoke.return_value = mock_price
        mock_info_tool.invoke.return_value = mock_info
        mock_fin_tool.invoke.return_value = mock_fin

        result = agent_graph.invoke({"query": "Tell me IBM's valuation and P/E ratio"})

        assert result["ticker"] == "IBM"
        assert result["intent"] == "fundamentals"
        mock_price_tool.invoke.assert_called_once()
        mock_info_tool.invoke.assert_called_once()
        mock_fin_tool.invoke.assert_called_once()
        mock_hist_tool.invoke.assert_not_called()
        assert "IBM Corp" in result["analysis"]


def test_graph_full_research_calls_all_tools():
    """Test full_research intent calls all stock tools."""
    mock_price = {"status": "success", "price": 250.0, "previous_close": 245.0, "change": 5.0, "change_percent": 2.04}
    mock_info = {"status": "success", "name": "Tesla Inc", "sector": "Consumer", "industry": "Auto", "country": "USA"}
    mock_fin = {"status": "success", "metrics": {"market_cap": 800000000000}}
    mock_hist = {"status": "success", "period": "1mo", "history": [{"date": "2026-03-30", "close": 250.0}]}
    mock_news = {"status": "unavailable", "news": [], "error": "Premium required"}

    with patch("backend.services.gemini_service.get_gemini_client", return_value=None), \
         patch("backend.agent.graph.get_stock_price") as mock_price_tool, \
         patch("backend.agent.graph.get_company_info") as mock_info_tool, \
         patch("backend.agent.graph.get_financial_summary") as mock_fin_tool, \
         patch("backend.agent.graph.get_stock_history") as mock_hist_tool, \
         patch("backend.agent.graph.search_stock_news") as mock_news_tool:

        mock_price_tool.invoke.return_value = mock_price
        mock_info_tool.invoke.return_value = mock_info
        mock_fin_tool.invoke.return_value = mock_fin
        mock_hist_tool.invoke.return_value = mock_hist
        mock_news_tool.invoke.return_value = mock_news

        result = agent_graph.invoke({"query": "Comprehensive research report on TSLA"})

        assert result["ticker"] == "TSLA"
        assert result["intent"] == "full_research"
        mock_price_tool.invoke.assert_called_once()
        mock_info_tool.invoke.assert_called_once()
        mock_fin_tool.invoke.assert_called_once()
        mock_hist_tool.invoke.assert_called_once()
        mock_news_tool.invoke.assert_called_once()
        assert "Tesla Inc" in result["analysis"]


def test_graph_gemini_synthesis_success():
    """Test analyse_node uses Gemini synthesis when available."""
    mock_gemini_resp = MagicMock()
    mock_gemini_resp.text = "# Gemini Stock Report\n\nApple is exhibiting strong momentum."

    with patch("backend.services.gemini_service.get_gemini_client") as mock_get_client, \
         patch("backend.agent.graph.get_stock_price") as mock_price_tool:

        mock_price_tool.invoke.return_value = {"status": "success", "price": 180.0}
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_gemini_resp
        mock_get_client.return_value = mock_client

        result = agent_graph.invoke({"query": "Price of AAPL"})

        assert "Gemini Stock Report" in result["analysis"]
        assert "Apple is exhibiting strong momentum." in result["analysis"]


def test_graph_gemini_quota_exhausted_deterministic_fallback():
    """Test that when Gemini raises QuotaExhausted / API error, deterministic report is returned."""
    with patch("backend.services.gemini_service.get_gemini_client") as mock_get_client, \
         patch("backend.agent.graph.get_stock_price") as mock_price_tool:

        mock_price_tool.invoke.return_value = {
            "status": "success",
            "price": 180.0,
            "previous_close": 178.0,
            "change": 2.0,
            "change_percent": 1.12,
        }
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("429 ResourceExhausted: Quota exceeded")
        mock_get_client.return_value = mock_client

        result = agent_graph.invoke({"query": "Price of AAPL"})

        assert result.get("error") is None
        assert "# Stock Research Report: AAPL" in result["analysis"]
        assert "Current Price**: $180.00" in result["analysis"]
        assert "deterministic market analysis engine" in result["analysis"]
