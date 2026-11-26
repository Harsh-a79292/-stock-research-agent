"""
tests/test_stock_tools.py
─────────────────────────
Unit tests for Alpha Vantage stock market data tools.
Tests price, historical OHLCV, company info, financial summary, and news tools
using mocked HTTP responses.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from backend.core.config import settings
from backend.tools.stock_tools import (
    get_company_info,
    get_financial_summary,
    get_stock_history,
    get_stock_price,
    search_stock_news,
)


@pytest.fixture(autouse=True)
def setup_api_key():
    """Ensure an API key is configured for tests by default."""
    orig_key = settings.alpha_vantage_api_key
    settings.alpha_vantage_api_key = "MOCK_ALPHA_KEY"
    yield
    settings.alpha_vantage_api_key = orig_key


def _create_mock_response(json_data, status_code=200):
    """Helper to create a mocked requests.Response object."""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status.return_value = None
    return mock_resp


# ── get_stock_price Tests ───────────────────────────────────────────────────


def test_get_stock_price_success():
    """Test get_stock_price with mocked Alpha Vantage TIME_SERIES_DAILY returning valid prices."""
    mock_data = {
        "Meta Data": {
            "1. Information": "Daily Prices (open, high, low, close) and Volumes",
            "2. Symbol": "AAPL",
            "3. Last Refreshed": "2026-03-30",
            "4. Output Size": "Compact",
            "5. Time Zone": "US/Eastern",
        },
        "Time Series (Daily)": {
            "2026-03-30": {
                "1. open": "152.0",
                "2. high": "156.0",
                "3. low": "151.0",
                "4. close": "155.0",
                "5. volume": "1200",
            },
            "2026-03-27": {
                "1. open": "150.0",
                "2. high": "155.0",
                "3. low": "149.0",
                "4. close": "152.0",
                "5. volume": "1000",
            },
        },
    }

    with patch("requests.get", return_value=_create_mock_response(mock_data)):
        result = get_stock_price.invoke({"ticker": "AAPL"})

        assert result["ticker"] == "AAPL"
        assert result["status"] == "success"
        assert result["price"] == 155.0
        assert result["previous_close"] == 152.0
        assert result["change"] == 3.0
        assert result["change_percent"] == 1.97
        assert "timestamp" in result
        assert "notice" in result


def test_get_stock_price_weekend_holiday_handling():
    """Test get_stock_price correctly handles weekend/holiday gaps in trading sessions."""
    mock_data = {
        "Time Series (Daily)": {
            "2026-03-30": {
                "1. open": "150.0",
                "2. high": "152.0",
                "3. low": "149.0",
                "4. close": "151.0",
                "5. volume": "6000",
            },
            "2026-03-27": {
                "1. open": "145.0",
                "2. high": "148.0",
                "3. low": "144.0",
                "4. close": "146.5",
                "5. volume": "5000",
            },
        }
    }

    with patch("requests.get", return_value=_create_mock_response(mock_data)):
        result = get_stock_price.invoke({"ticker": "AAPL"})

        assert result["status"] == "success"
        assert result["price"] == 151.0
        assert result["previous_close"] == 146.5
        assert result["change"] == 4.5
        assert result["change_percent"] == 3.07


def test_get_stock_price_single_session():
    """Test get_stock_price when only one trading session is available."""
    mock_data = {
        "Time Series (Daily)": {
            "2026-03-30": {
                "1. open": "150.0",
                "2. high": "152.0",
                "3. low": "149.0",
                "4. close": "151.0",
                "5. volume": "6000",
            }
        }
    }

    with patch("requests.get", return_value=_create_mock_response(mock_data)):
        result = get_stock_price.invoke({"ticker": "AAPL"})

        assert result["status"] == "success"
        assert result["price"] == 151.0
        assert result["previous_close"] == 151.0
        assert result["change"] == 0.0
        assert result["change_percent"] == 0.0


def test_get_stock_price_missing_api_key():
    """Test get_stock_price when Alpha Vantage API key is missing."""
    settings.alpha_vantage_api_key = ""
    result = get_stock_price.invoke({"ticker": "AAPL"})

    assert result["status"] == "error"
    assert result["price"] is None
    assert "API key is not configured" in result["error"]


def test_get_stock_price_rate_limit():
    """Test get_stock_price when Alpha Vantage rate limit is reached."""
    mock_data = {
        "Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute and 25 calls per day."
    }

    with patch("requests.get", return_value=_create_mock_response(mock_data)):
        result = get_stock_price.invoke({"ticker": "AAPL"})

        assert result["status"] == "error"
        assert result["price"] is None
        assert "rate limit exceeded" in result["error"]


def test_get_stock_price_api_error():
    """Test get_stock_price when Alpha Vantage returns an error message."""
    mock_data = {
        "Error Message": "Invalid API call. Please check the parameters."
    }

    with patch("requests.get", return_value=_create_mock_response(mock_data)):
        result = get_stock_price.invoke({"ticker": "INVALID"})

        assert result["status"] == "error"
        assert result["price"] is None
        assert "Alpha Vantage API error" in result["error"]


def test_get_stock_price_empty_response():
    """Test get_stock_price when Alpha Vantage returns empty response."""
    with patch("requests.get", return_value=_create_mock_response({})):
        result = get_stock_price.invoke({"ticker": "AAPL"})

        assert result["status"] == "error"
        assert result["price"] is None
        assert result["previous_close"] is None
        assert "error" in result


def test_get_stock_price_network_timeout():
    """Test get_stock_price handling network timeout gracefully."""
    with patch("requests.get", side_effect=requests.exceptions.Timeout("Request timed out")):
        result = get_stock_price.invoke({"ticker": "AAPL"})

        assert result["status"] == "error"
        assert result["price"] is None
        assert "timed out" in result["error"]


def test_get_stock_price_network_exception():
    """Test get_stock_price handling network exceptions gracefully."""
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Failed to connect")):
        result = get_stock_price.invoke({"ticker": "AAPL"})

        assert result["status"] == "error"
        assert result["price"] is None
        assert "Network error" in result["error"]


def test_get_stock_price_malformed_json():
    """Test get_stock_price handling malformed JSON response."""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("Invalid JSON string")
    mock_resp.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_resp):
        result = get_stock_price.invoke({"ticker": "AAPL"})

        assert result["status"] == "error"
        assert result["price"] is None
        assert "Malformed JSON" in result["error"]


def test_get_stock_price_invalid_ticker():
    """Test get_stock_price with invalid or empty ticker strings."""
    for invalid_ticker in ["", "   ", None, "A" * 20]:
        result = get_stock_price.invoke({"ticker": invalid_ticker})
        assert result["status"] == "error"
        assert result["price"] is None


# ── get_stock_history Tests ─────────────────────────────────────────────────


def test_get_stock_history_success():
    """Test get_stock_history returns expected OHLCV records."""
    mock_data = {
        "Time Series (Daily)": {
            "2026-01-01": {
                "1. open": "100.0",
                "2. high": "105.0",
                "3. low": "98.0",
                "4. close": "102.0",
                "5. volume": "5000",
            }
        }
    }

    with patch("requests.get", return_value=_create_mock_response(mock_data)):
        result = get_stock_history.invoke({"ticker": "MSFT", "period": "1mo"})

        assert result["ticker"] == "MSFT"
        assert result["period"] == "1mo"
        assert result["status"] == "success"
        assert len(result["history"]) == 1
        assert result["history"][0]["date"] == "2026-01-01"
        assert result["history"][0]["open"] == 100.0
        assert result["history"][0]["high"] == 105.0
        assert result["history"][0]["low"] == 98.0
        assert result["history"][0]["close"] == 102.0
        assert result["history"][0]["volume"] == 5000


def test_get_stock_history_period_filtering():
    """Test get_stock_history period filtering limits records appropriately."""
    sessions = {}
    for i in range(1, 15):
        day_str = f"2026-01-{i:02d}"
        sessions[day_str] = {
            "1. open": "100.0",
            "2. high": "105.0",
            "3. low": "98.0",
            "4. close": "100.0",
            "5. volume": "1000",
        }
    mock_data = {"Time Series (Daily)": sessions}

    with patch("requests.get", return_value=_create_mock_response(mock_data)):
        result_5d = get_stock_history.invoke({"ticker": "MSFT", "period": "5d"})
        assert result_5d["status"] == "success"
        assert len(result_5d["history"]) == 5

        result_1d = get_stock_history.invoke({"ticker": "MSFT", "period": "1d"})
        assert result_1d["status"] == "success"
        assert len(result_1d["history"]) == 1


def test_get_stock_history_empty():
    """Test get_stock_history with empty response."""
    with patch("requests.get", return_value=_create_mock_response({})):
        result = get_stock_history.invoke({"ticker": "MSFT", "period": "1mo"})

        assert result["status"] == "error"
        assert result["history"] == []


# ── get_company_info Tests ──────────────────────────────────────────────────


def test_get_company_info_success():
    """Test get_company_info returns corporate profile details from OVERVIEW."""
    mock_overview = {
        "Symbol": "AAPL",
        "Name": "Apple Inc.",
        "Sector": "Technology",
        "Industry": "Consumer Electronics",
        "Country": "USA",
        "MarketCapitalization": "3000000000000",
        "TrailingPE": "30.5",
        "ForwardPE": "28.0",
        "DividendYield": "0.005",
        "52WeekHigh": "199.62",
        "52WeekLow": "164.08",
        "Currency": "USD",
    }

    with patch("requests.get", return_value=_create_mock_response(mock_overview)):
        result = get_company_info.invoke({"ticker": "AAPL"})

        assert result["ticker"] == "AAPL"
        assert result["status"] == "success"
        assert result["name"] == "Apple Inc."
        assert result["sector"] == "Technology"
        assert result["industry"] == "Consumer Electronics"
        assert result["country"] == "USA"
        assert result["market_cap"] == 3000000000000
        assert result["pe_ratio"] == 30.5
        assert result["forward_pe"] == 28.0
        assert result["dividend_yield"] == 0.005
        assert result["fifty_two_week_high"] == 199.62
        assert result["fifty_two_week_low"] == 164.08
        assert result["currency"] == "USD"


def test_get_company_info_not_found():
    """Test get_company_info when ticker is not found (empty dict from Alpha Vantage)."""
    with patch("requests.get", return_value=_create_mock_response({})):
        result = get_company_info.invoke({"ticker": "INVALID"})

        assert result["status"] == "error"
        assert result["info"] == {}
        assert "No company info found" in result["error"]


# ── get_financial_summary Tests ─────────────────────────────────────────────


def test_get_financial_summary_success():
    """Test get_financial_summary returns key financial metrics."""
    mock_overview = {
        "Symbol": "MSFT",
        "MarketCapitalization": "3100000000000",
        "TrailingPE": "35.2",
        "ForwardPE": "30.1",
        "PriceToBookRatio": "12.5",
        "ProfitMargin": "0.36",
        "ReturnOnEquityTTM": "0.39",
        "RevenueTTM": "245000000000",
        "QuarterlyRevenueGrowthYOY": "0.15",
        "TotalDebt": "100000000000",
        "FreeCashflow": "70000000000",
    }

    with patch("requests.get", return_value=_create_mock_response(mock_overview)):
        result = get_financial_summary.invoke({"ticker": "MSFT"})

        assert result["status"] == "success"
        metrics = result["metrics"]
        assert metrics["market_cap"] == 3100000000000
        assert metrics["trailing_pe"] == 35.2
        assert metrics["forward_pe"] == 30.1
        assert metrics["price_to_book"] == 12.5
        assert metrics["profit_margins"] == 0.36
        assert metrics["return_on_equity"] == 0.39
        assert metrics["total_revenue"] == 245000000000
        assert metrics["revenue_growth"] == 0.15
        assert metrics["total_debt"] == 100000000000
        assert metrics["free_cashflow"] == 70000000000


def test_get_financial_summary_missing_metrics():
    """Test get_financial_summary handles missing or 'None' metrics returning None rather than fabricated values."""
    mock_overview = {
        "Symbol": "TSLA",
        "MarketCapitalization": "800000000000",
        "TrailingPE": "None",
        "ForwardPE": "-",
        "PriceToBookRatio": "N/A",
        "ProfitMargin": "null",
        "ReturnOnEquityTTM": None,
        "RevenueTTM": "95000000000",
        "QuarterlyRevenueGrowthYOY": "None",
    }

    with patch("requests.get", return_value=_create_mock_response(mock_overview)):
        result = get_financial_summary.invoke({"ticker": "TSLA"})

        assert result["status"] == "success"
        metrics = result["metrics"]
        assert metrics["market_cap"] == 800000000000
        assert metrics["total_revenue"] == 95000000000
        assert metrics["trailing_pe"] is None
        assert metrics["forward_pe"] is None
        assert metrics["price_to_book"] is None
        assert metrics["profit_margins"] is None
        assert metrics["return_on_equity"] is None
        assert metrics["revenue_growth"] is None
        assert metrics["total_debt"] is None
        assert metrics["free_cashflow"] is None


def test_get_financial_summary_all_empty_returns_error():
    """Test get_financial_summary when response has no valid metrics."""
    with patch("requests.get", return_value=_create_mock_response({})):
        result = get_financial_summary.invoke({"ticker": "TSLA"})

        assert result["status"] == "error"
        assert "No financial summary data found" in result["error"]


# ── search_stock_news Tests ─────────────────────────────────────────────────


def test_search_stock_news_unavailable():
    """Test search_stock_news returns a consistent structured response when RSS feeds fail."""
    with patch("backend.tools.stock_tools.requests.get", side_effect=RuntimeError("Feed unavailable")):
        result = search_stock_news.invoke({"ticker": "AAPL"})

    assert isinstance(result, dict)
    assert result["status"] == "unavailable"
    assert result["ticker"] == "AAPL"
    assert result["news"] == []
    assert "unavailable" in result["error"].lower()
    assert "notice" in result


def test_search_stock_news_without_alpha_vantage_key():
    """Test search_stock_news works with free RSS feeds even when ALPHA_VANTAGE_API_KEY is empty."""
    settings.alpha_vantage_api_key = ""
    mock_resp = MagicMock()
    mock_resp.text = """<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0"><channel><item>
      <title>Apple gains on strong demand</title>
      <link>https://example.com/1</link>
      <pubDate>Thu, 26 Nov 2026 05:00:00 +0000</pubDate>
      <source>Reuters</source>
    </item></channel></rss>"""
    mock_resp.raise_for_status.return_value = None

    with patch("backend.tools.stock_tools.requests.get", return_value=mock_resp):
        result = search_stock_news.invoke({"ticker": "AAPL"})

    assert result["status"] == "success"
    assert len(result["news"]) == 1


def test_search_stock_news_invalid_ticker():
    """Test search_stock_news with invalid ticker."""
    result = search_stock_news.invoke({"ticker": ""})

    assert result["status"] == "error"
    assert result["news"] == []


# ── API Key Protection Test ─────────────────────────────────────────────────


def test_api_key_not_exposed_in_network_error():
    """Test that secret API keys are never exposed in error messages."""
    settings.alpha_vantage_api_key = "TOP_SECRET_API_KEY_123"
    with patch(
        "requests.get",
        side_effect=requests.exceptions.ConnectionError(
            "Failed connecting to https://www.alphavantage.co/query?apikey=TOP_SECRET_API_KEY_123"
        ),
    ):
        result = get_stock_price.invoke({"ticker": "AAPL"})

        assert result["status"] == "error"
        assert "TOP_SECRET_API_KEY_123" not in result["error"]
        assert "***" in result["error"]
