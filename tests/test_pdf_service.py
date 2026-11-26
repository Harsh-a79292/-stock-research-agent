"""
tests/test_pdf_service.py
─────────────────────────
Task 4 Unit Tests: PDF Generation from Agent Research Results.
Tests PDF generation, data integrity, missing data resilience,
PDF document readability via pypdf, and markdown parsing.
"""

import io
from pathlib import Path
from unittest.mock import patch
import pypdf
import pytest

from backend.agent.graph import agent_graph
from backend.services.pdf_service import generate_pdf_report


@pytest.fixture
def sample_agent_state():
    """Realistic complete AgentState output from LangGraph agent."""
    return {
        "query": "Full research report on Apple AAPL",
        "ticker": "AAPL",
        "intent": "full_research",
        "error": None,
        "tool_results": {
            "price": {
                "status": "success",
                "ticker": "AAPL",
                "price": 185.50,
                "previous_close": 180.00,
                "change": 5.50,
                "change_percent": 3.06,
                "timestamp": "2026-03-30T16:00:00Z",
                "notice": "Data provided via Alpha Vantage.",
            },
            "company_info": {
                "status": "success",
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "country": "USA",
                "currency": "USD",
                "fifty_two_week_high": 199.62,
                "fifty_two_week_low": 164.08,
            },
            "financial_summary": {
                "status": "success",
                "ticker": "AAPL",
                "metrics": {
                    "market_cap": 3000000000000,
                    "trailing_pe": 30.50,
                    "forward_pe": 28.00,
                    "price_to_book": 35.20,
                    "profit_margins": 0.255,
                    "return_on_equity": 0.420,
                    "total_revenue": 385000000000,
                    "revenue_growth": 0.082,
                },
            },
            "history": {
                "status": "success",
                "ticker": "AAPL",
                "period": "1mo",
                "history": [
                    {"date": "2026-03-27", "open": 180.0, "high": 182.0, "low": 179.0, "close": 180.0, "volume": 1200000},
                    {"date": "2026-03-30", "open": 182.0, "high": 186.0, "low": 181.0, "close": 185.5, "volume": 1500000},
                ],
            },
            "news": {
                "status": "unavailable",
                "ticker": "AAPL",
                "news": [],
                "error": "News requires premium subscription",
            },
        },
        "analysis": (
            "# Executive Summary\n\n"
            "Apple Inc. (**AAPL**) maintains a dominant position in consumer technology with solid ecosystem growth.\n\n"
            "## Valuation & Price Action\n"
            "- Current Price is **$185.50**, up **+3.06%** over the previous close.\n"
            "- Market Capitalization stands at **$3.00T** with a Trailing P/E of **30.50x**.\n\n"
            "## Risk Factors\n"
            "> Regulatory scrutiny and hardware replacement cycles remain the primary headwinds.\n\n"
            "--- \n"
            "*Research compiled by AI Stock Research Agent.*"
        ),
    }


def test_pdf_generates_from_actual_agent_results(sample_agent_state):
    """Test 1: Verify PDF generates cleanly from agent results into valid PDF bytes."""
    pdf_bytes = generate_pdf_report(sample_agent_state)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_pdf_contains_correct_stock_data_and_analysis(sample_agent_state):
    """Test 2: Verify PDF contains correct stock data, metrics, and text using pypdf."""
    pdf_bytes = generate_pdf_report(sample_agent_state)
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))

    assert len(reader.pages) >= 1
    full_text = "".join(page.extract_text() for page in reader.pages)

    # Core data verifications
    assert "EQUITY RESEARCH REPORT: AAPL" in full_text
    assert "Apple Inc." in full_text
    assert "$185.50" in full_text
    assert "+5.50 (+3.06%)" in full_text
    assert "$3.00T" in full_text
    assert "30.50x" in full_text
    assert "28.00x" in full_text
    assert "Technology" in full_text
    assert "$385.00B" in full_text
    assert "25.50%" in full_text

    # Analysis section verifications
    assert "Executive Summary" in full_text
    assert "Valuation & Price Action" in full_text
    assert "Regulatory scrutiny" in full_text


def test_pdf_missing_data_handled_safely():
    """Test 3: Verify missing or corrupted fields are safely displayed without crashing."""
    sparse_state = {
        "query": "Price of TSLA",
        "ticker": "TSLA",
        "intent": "price_check",
        "tool_results": {
            "price": {
                "status": "error",
                "error": "Data unavailable",
                "price": None,
                "previous_close": None,
                "change": None,
                "change_percent": None,
            },
            "company_info": None,
            "financial_summary": {},
        },
        "analysis": "",
    }

    pdf_bytes = generate_pdf_report(sparse_state)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    extracted = "".join(page.extract_text() for page in reader.pages)

    assert "EQUITY RESEARCH REPORT: TSLA" in extracted
    # Missing data should fall back to dashes / placeholders, never crashing
    assert "—" in extracted


def test_pdf_opens_correctly_and_formatting_is_readable(tmp_path, sample_agent_state):
    """Test 4: Verify PDF written to disk opens correctly and has clean formatting."""
    file_path = tmp_path / "AAPL_Research_Report.pdf"
    pdf_bytes = generate_pdf_report(sample_agent_state, output_path=file_path)

    assert file_path.exists()
    assert file_path.stat().st_size == len(pdf_bytes)

    reader = pypdf.PdfReader(str(file_path))
    assert not reader.is_encrypted
    assert len(reader.pages) >= 1

    first_page_text = reader.pages[0].extract_text()
    assert len(first_page_text.strip()) > 200
    normalized_text = " ".join(first_page_text.split())
    assert "Alpha Vantage" in normalized_text


def test_pdf_special_characters_and_html_escaping():
    """Test 5: Verify special chars (&, <, >, quotes, code spans) don't break XML parsing."""
    state_with_special_chars = {
        "query": "Research AT&T <T> & S&P 500",
        "ticker": "T",
        "intent": "full_research",
        "tool_results": {},
        "analysis": (
            "# AT&T Analysis <2026>\n\n"
            "Revenue is > $100B & margins are < 20%.\n"
            "- Item with `code_snippet` & **bold** & *italic*\n"
            "> Quote with 'single' and \"double\" quotes & ampersands."
        ),
    }

    pdf_bytes = generate_pdf_report(state_with_special_chars)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    text = reader.pages[0].extract_text()
    assert "AT&T" in text
    assert "Revenue is > $100B" in text


def test_pdf_direct_integration_from_agent_graph():
    """Test 6: Verify end-to-end integration by feeding live graph output directly into PDF generator."""
    mock_price = {
        "status": "success",
        "ticker": "IBM",
        "price": 190.25,
        "previous_close": 188.00,
        "change": 2.25,
        "change_percent": 1.20,
    }
    mock_info = {
        "status": "success",
        "name": "International Business Machines",
        "sector": "Technology",
        "industry": "IT Services",
        "country": "USA",
    }
    mock_fin = {
        "status": "success",
        "metrics": {"market_cap": 210000000000, "trailing_pe": 21.5},
    }

    with patch("backend.services.gemini_service.get_gemini_client", return_value=None), \
         patch("backend.agent.graph.get_stock_price") as mock_p, \
         patch("backend.agent.graph.get_company_info") as mock_i, \
         patch("backend.agent.graph.get_financial_summary") as mock_f:

        mock_p.invoke.return_value = mock_price
        mock_i.invoke.return_value = mock_info
        mock_f.invoke.return_value = mock_fin

        # Invoke the actual agent_graph
        state = agent_graph.invoke({"query": "Analyze IBM fundamentals"})

        # Pass directly into generate_pdf_report
        pdf_bytes = generate_pdf_report(state)

        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        full_text = reader.pages[0].extract_text()

        assert "EQUITY RESEARCH REPORT: IBM" in full_text
        assert "International Business Machines" in full_text
        assert "$190.25" in full_text
        assert "$210.00B" in full_text
