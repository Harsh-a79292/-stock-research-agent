"""
tests/test_news_integration.py
──────────────────────────────
Focused unit tests for Task 9: Latest Financial News Integration.
"""

from unittest.mock import MagicMock, patch

from backend.services.gemini_service import summarize_stock_news
from backend.services.pdf_service import generate_pdf_report
from backend.tools.stock_tools import search_stock_news

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Yahoo Finance</title>
    <item>
      <title>Apple beats Q4 earnings expectations on strong Services growth</title>
      <link>https://example.com/news/apple-beats</link>
      <pubDate>Thu, 26 Nov 2026 05:00:00 +0000</pubDate>
      <source>Reuters</source>
    </item>
    <item>
      <title>Apple faces supply chain warning ahead of holiday quarter</title>
      <link>https://example.com/news/apple-supply</link>
      <pubDate>Wed, 25 Nov 2026 18:00:00 +0000</pubDate>
      <source>Bloomberg</source>
    </item>
  </channel>
</rss>"""


def test_search_stock_news_primary_rss():
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_RSS
    mock_resp.raise_for_status.return_value = None

    with patch("backend.tools.stock_tools.requests.get", return_value=mock_resp) as mock_get:
        res = search_stock_news.invoke({"ticker": "AAPL"})

    assert res["status"] == "success"
    assert res["ticker"] == "AAPL"
    assert res["feed_source"] == "Yahoo Finance RSS"
    assert len(res["news"]) == 2
    assert res["news"][0]["title"].startswith("Apple beats")
    assert res["news"][0]["source"] == "Reuters"
    assert res["news"][0]["url"] == "https://example.com/news/apple-beats"
    assert res["news"][0]["published_at"] == "Thu, 26 Nov 2026 05:00:00 +0000"
    assert res["news"][0]["sentiment"] == "Bullish"
    assert res["news"][1]["sentiment"] == "Bearish"
    mock_get.assert_called_once()


def test_search_stock_news_fallback_rss_on_primary_failure():
    fallback_resp = MagicMock()
    fallback_resp.text = SAMPLE_RSS
    fallback_resp.raise_for_status.return_value = None

    with patch(
        "backend.tools.stock_tools.requests.get",
        side_effect=[RuntimeError("Yahoo timeout"), fallback_resp],
    ) as mock_get:
        res = search_stock_news.invoke({"ticker": "MSFT"})

    assert res["status"] == "success"
    assert res["feed_source"] == "Google News RSS"
    assert len(res["news"]) == 2
    assert mock_get.call_count == 2


def test_search_stock_news_graceful_failure():
    with patch(
        "backend.tools.stock_tools.requests.get",
        side_effect=RuntimeError("Network unreachable"),
    ):
        res = search_stock_news.invoke({"ticker": "NVDA"})

    assert res["status"] == "unavailable"
    assert res["news"] == []
    assert "Network unreachable" in res["error"]


def test_summarize_stock_news_gemini_and_fallback():
    articles = [
        {"title": "NVDA surges on AI chip demand", "source": "Reuters", "published_at": "Today", "sentiment": "Bullish"},
    ]

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(text="NVIDIA rallied on strong AI demand.")
    with patch("backend.services.gemini_service.get_gemini_client", return_value=mock_client):
        summary = summarize_stock_news("NVDA", articles)
    assert "NVIDIA rallied" in summary

    with patch("backend.services.gemini_service.get_gemini_client", return_value=None):
        fallback = summarize_stock_news("NVDA", articles)
    assert "Bullish" in fallback
    assert "NVDA surges" in fallback


def test_pdf_includes_news_section():
    state = {
        "query": "Full research on AAPL",
        "ticker": "AAPL",
        "intent": "full_research",
        "analysis": "# Executive Summary\nApple remains resilient.",
        "tool_results": {
            "price": {"status": "success", "price": 210.5, "change": 2.1, "change_percent": 1.0},
            "company_info": {"status": "success", "name": "Apple Inc.", "sector": "Technology"},
            "financial_summary": {"status": "success", "metrics": {}},
            "news": {
                "status": "success",
                "summary": "Apple coverage is positive following strong Services growth.",
                "news": [
                    {
                        "title": "Apple beats Q4 earnings",
                        "source": "Reuters",
                        "url": "https://example.com/1",
                        "published_at": "2026-11-26",
                        "sentiment": "Bullish",
                    }
                ],
            },
        },
    }
    pdf_bytes = generate_pdf_report(state)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
