"""
tests/test_frontend.py
──────────────────────
Unit tests for the Phase 3 Streamlit frontend components:
chart generation, formatting helpers, and agent output integration.
"""

from unittest.mock import MagicMock, patch
import plotly.graph_objects as go
import pytest

from frontend.app import (
    build_plotly_chart,
    format_curr,
    format_large_num,
    format_pct,
    format_ratio,
)
from backend.agent.graph import agent_graph


# ── Charting Function Tests ───────────────────────────────────────────────────

def test_build_plotly_chart_success():
    """Test build_plotly_chart generates a two-panel candlestick + volume chart."""
    mock_history = {
        "status": "success",
        "ticker": "AAPL",
        "period": "1mo",
        "history": [
            {
                "date": "2026-03-27",
                "open": 172.0,
                "high": 175.0,
                "low": 171.0,
                "close": 174.0,
                "volume": 1200000,
            },
            {
                "date": "2026-03-30",
                "open": 174.5,
                "high": 178.0,
                "low": 173.5,
                "close": 177.5,
                "volume": 1500000,
            },
        ],
    }

    fig = build_plotly_chart(mock_history, "AAPL")
    assert isinstance(fig, go.Figure)
    # Expect 2 traces: 1 Candlestick + 1 Volume Bar
    assert len(fig.data) == 2
    assert isinstance(fig.data[0], go.Candlestick)
    assert isinstance(fig.data[1], go.Bar)
    assert "AAPL" in fig.layout.title.text


def test_build_plotly_chart_empty_or_error():
    """Test build_plotly_chart returns None when data is missing or marked as error."""
    assert build_plotly_chart(None, "AAPL") is None
    assert build_plotly_chart({}, "AAPL") is None
    assert build_plotly_chart({"status": "error", "history": []}, "AAPL") is None
    assert build_plotly_chart({"status": "success", "history": []}, "AAPL") is None


# ── Formatting Helper Tests ───────────────────────────────────────────────────

def test_format_curr():
    """Test currency formatting with various types."""
    assert format_curr(185.5) == "$185.50"
    assert format_curr("150.0") == "$150.00"
    assert format_curr(None) == "N/A"
    assert format_curr("invalid") == "N/A"


def test_format_large_num():
    """Test large number formatting into Trillions, Billions, Millions."""
    assert format_large_num(3.1e12) == "$3.10T"
    assert format_large_num(250e9) == "$250.00B"
    assert format_large_num(50e6) == "$50.00M"
    assert format_large_num(5000) == "$5,000"
    assert format_large_num(None) == "—"
    assert format_large_num("None") == "—"


def test_format_ratio():
    """Test multiplier ratio formatting."""
    assert format_ratio(25.456) == "25.46x"
    assert format_ratio("30.2") == "30.20x"
    assert format_ratio(None) == "—"
    assert format_ratio("N/A") == "—"


def test_format_pct():
    """Test percentage formatting."""
    assert format_pct(0.155) == "15.50%"
    assert format_pct("-0.032") == "-3.20%"
    assert format_pct(None) == "—"
    assert format_pct("invalid") == "—"


# ── Integration with LangGraph Agent State ─────────────────────────────────────

def test_frontend_consumes_agent_price_check():
    """Verify that agent_graph price_check output has all fields consumed by app.py."""
    mock_price = {
        "status": "success",
        "ticker": "IBM",
        "price": 182.50,
        "previous_close": 180.00,
        "change": 2.50,
        "change_percent": 1.39,
        "timestamp": "2026-03-30T10:00:00Z",
    }

    with patch("backend.services.gemini_service.get_gemini_client", return_value=None), \
         patch("backend.agent.graph.get_stock_price") as mock_price_tool:

        mock_price_tool.invoke.return_value = mock_price

        state = agent_graph.invoke({"query": "What is the stock price of IBM?"})

        assert state["ticker"] == "IBM"
        assert state["intent"] == "price_check"
        assert "price" in state["tool_results"]
        # Verify formatting helpers work seamlessly on this real tool payload
        price_val = state["tool_results"]["price"]["price"]
        assert format_curr(price_val) == "$182.50"


def test_frontend_consumes_agent_error_gracefully():
    """Verify that an invalid query returns error state that the frontend renders cleanly."""
    with patch("backend.services.gemini_service.get_gemini_client", return_value=None):
        state = agent_graph.invoke({"query": "How is the weather today?"})

        assert state["error"] is not None
        assert state["ticker"] is None
        assert "Stock Research Error" in state["analysis"]
