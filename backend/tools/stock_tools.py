"""
tools/stock_tools.py
────────────────────
Stock market data tools powered by Alpha Vantage.
Provides price, historical chart data, company info, financials, and news search.
"""

import json
import logging
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests
from langchain_core.tools import tool

from backend.core.config import settings

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
DATA_DELAY_NOTICE = "Data provided via Alpha Vantage. Market data may be delayed and is not guaranteed real-time."


def _validate_ticker(ticker: any) -> tuple[bool, str]:
    """Validate ticker symbol format."""
    if not isinstance(ticker, str):
        return False, "Ticker must be a string."
    clean = ticker.strip().upper()
    if not clean:
        return False, "Ticker symbol cannot be empty."
    if len(clean) > 15:
        return False, f"Ticker symbol too long: {clean}"
    return True, clean


def _safe_float(val) -> float | None:
    """Safely convert a value to float rounded to 2 decimal places, handling None, NaN, inf, 'None', '-'."""
    if val is None:
        return None
    if isinstance(val, str):
        v = val.strip().lower()
        if not v or v in ("none", "null", "nan", "n/a", "-"):
            return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 2)
    except (TypeError, ValueError):
        return None


def _safe_float_raw(val) -> float | None:
    """Safely convert a value to float without rounding (for metrics/ratios)."""
    if val is None:
        return None
    if isinstance(val, str):
        v = val.strip().lower()
        if not v or v in ("none", "null", "nan", "n/a", "-"):
            return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:
    """Safely convert a value to int, handling None, NaN, 'None', '-'."""
    if val is None:
        return None
    if isinstance(val, str):
        v = val.strip().lower()
        if not v or v in ("none", "null", "nan", "n/a", "-"):
            return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _safe_str(val) -> str | None:
    """Safely convert a value to stripped non-empty string, handling 'None', 'N/A', '-'."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "nan", "n/a", "-"):
        return None
    return s


def _fetch_alpha_vantage(function: str, extra_params: dict | None = None) -> tuple[bool, dict]:
    """
    Internal helper to call the Alpha Vantage API with error, rate limit, and timeout handling.
    Safely redacts API key from logs and error output.

    Returns:
        (is_success, data_or_error_dict)
    """
    api_key = settings.alpha_vantage_api_key.strip() if settings.alpha_vantage_api_key else ""
    if not api_key:
        return False, {"error": "Alpha Vantage API key is not configured. Please set ALPHA_VANTAGE_API_KEY."}

    params = {
        "function": function,
        "apikey": api_key,
    }
    if extra_params:
        params.update(extra_params)

    try:
        response = requests.get(ALPHA_VANTAGE_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.Timeout:
        logger.error("Alpha Vantage API request timed out.")
        return False, {"error": "Alpha Vantage API request timed out."}
    except requests.exceptions.RequestException as e:
        err_msg = str(e).replace(api_key, "***") if api_key else str(e)
        logger.error(f"Network error calling Alpha Vantage API ({function}): {err_msg}")
        return False, {"error": f"Network error connecting to Alpha Vantage API: {err_msg}"}
    except (ValueError, json.JSONDecodeError):
        logger.error(f"Malformed JSON response from Alpha Vantage API for function {function}")
        return False, {"error": "Malformed JSON response received from Alpha Vantage API."}

    if not isinstance(data, dict):
        return False, {"error": "Unexpected response format from Alpha Vantage API."}

    if "Error Message" in data:
        err = data["Error Message"]
        logger.warning(f"Alpha Vantage API error ({function}): {err}")
        return False, {"error": f"Alpha Vantage API error: {err}"}

    if "Note" in data:
        note = data["Note"]
        logger.warning(f"Alpha Vantage rate limit reached ({function}): {note}")
        return False, {"error": f"Alpha Vantage rate limit exceeded: {note}"}

    if "Information" in data:
        info_msg = data["Information"]
        logger.warning(f"Alpha Vantage API notice ({function}): {info_msg}")
        # When information indicates frequency limit or lack of data
        if function == "TIME_SERIES_DAILY" and "Time Series (Daily)" not in data:
            return False, {"error": f"Alpha Vantage API notice: {info_msg}"}
        if function == "OVERVIEW" and "Symbol" not in data:
            return False, {"error": f"Alpha Vantage API notice: {info_msg}"}

    return True, data


@tool
def get_stock_price(ticker: str | None = "") -> dict:
    """
    Fetch the latest stock price, previous close, and calculate absolute and percentage price change.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL', 'TSLA').

    Returns:
        A dict with current price, previous close, change, percentage change, timestamp, and status.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    valid, clean_ticker = _validate_ticker(ticker)
    if not valid:
        return {
            "ticker": str(ticker).strip().upper() if ticker and isinstance(ticker, str) else "",
            "price": None,
            "previous_close": None,
            "change": None,
            "change_percent": None,
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": clean_ticker,
        }

    success, data = _fetch_alpha_vantage(
        function="TIME_SERIES_DAILY",
        extra_params={"symbol": clean_ticker, "outputsize": "compact"},
    )
    if not success:
        return {
            "ticker": clean_ticker,
            "price": None,
            "previous_close": None,
            "change": None,
            "change_percent": None,
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": data.get("error", f"Failed to fetch stock price for {clean_ticker}"),
        }

    time_series = data.get("Time Series (Daily)")
    if not time_series or not isinstance(time_series, dict):
        return {
            "ticker": clean_ticker,
            "price": None,
            "previous_close": None,
            "change": None,
            "change_percent": None,
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": f"No daily time series data found for ticker: {clean_ticker}",
        }

    sorted_dates = sorted(time_series.keys())
    valid_sessions = []
    for d in sorted_dates:
        session = time_series.get(d)
        if isinstance(session, dict):
            c = _safe_float(session.get("4. close") or session.get("close"))
            if c is not None:
                valid_sessions.append((d, c))

    if not valid_sessions:
        return {
            "ticker": clean_ticker,
            "price": None,
            "previous_close": None,
            "change": None,
            "change_percent": None,
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": f"No valid close price data found for {clean_ticker}",
        }

    _, current_price = valid_sessions[-1]
    if len(valid_sessions) >= 2:
        _, prev_close = valid_sessions[-2]
        change = current_price - prev_close
        change_percent = (change / prev_close) * 100 if prev_close else 0.0
    else:
        prev_close = current_price
        change = 0.0
        change_percent = 0.0

    return {
        "ticker": clean_ticker,
        "price": round(current_price, 2),
        "previous_close": round(prev_close, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "timestamp": timestamp,
        "notice": DATA_DELAY_NOTICE,
        "status": "success",
    }


@tool
def get_stock_history(ticker: str | None = "", period: str | None = "1mo") -> dict:
    """
    Fetch historical OHLCV data for a stock supporting periods like 1d, 5d, 1mo, 3mo, 6mo, 1y.

    Args:
        ticker: Stock ticker symbol.
        period: Time period (e.g. '1d', '5d', '1mo', '3mo', '6mo', '1y').

    Returns:
        A dict containing historical records, timestamp, and status.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    valid, clean_ticker = _validate_ticker(ticker)
    if not valid:
        return {
            "ticker": str(ticker).strip().upper() if ticker and isinstance(ticker, str) else "",
            "period": period,
            "history": [],
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": clean_ticker,
        }

    clean_period = period.strip().lower() if isinstance(period, str) else "1mo"
    valid_periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
    if clean_period not in valid_periods:
        clean_period = "1mo"

    success, data = _fetch_alpha_vantage(
        function="TIME_SERIES_DAILY",
        extra_params={"symbol": clean_ticker, "outputsize": "compact"},
    )
    if not success:
        return {
            "ticker": clean_ticker,
            "period": clean_period,
            "history": [],
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": data.get("error", f"Failed to fetch stock history for {clean_ticker}"),
        }

    time_series = data.get("Time Series (Daily)")
    if not time_series or not isinstance(time_series, dict):
        return {
            "ticker": clean_ticker,
            "period": clean_period,
            "history": [],
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": f"No historical data available for {clean_ticker}",
        }

    sorted_dates = sorted(time_series.keys())
    records = []
    for d in sorted_dates:
        session = time_series.get(d)
        if not isinstance(session, dict):
            continue
        o = _safe_float(session.get("1. open") or session.get("open"))
        h = _safe_float(session.get("2. high") or session.get("high"))
        l = _safe_float(session.get("3. low") or session.get("low"))
        c = _safe_float(session.get("4. close") or session.get("close"))
        v = _safe_int(session.get("5. volume") or session.get("volume"))

        if c is None:
            continue

        records.append({
            "date": d,
            "open": o if o is not None else c,
            "high": h if h is not None else c,
            "low": l if l is not None else c,
            "close": c,
            "volume": v if v is not None else 0,
        })

    # Period limit for compact output (which contains up to ~100 trading sessions)
    period_limit = {
        "1d": 1,
        "5d": 5,
        "1mo": 22,
        "3mo": 66,
    }
    if clean_period in period_limit:
        records = records[-period_limit[clean_period]:]

    if not records:
        return {
            "ticker": clean_ticker,
            "period": clean_period,
            "history": [],
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": f"No valid historical records found for {clean_ticker}",
        }

    return {
        "ticker": clean_ticker,
        "period": clean_period,
        "history": records,
        "timestamp": timestamp,
        "notice": DATA_DELAY_NOTICE,
        "status": "success",
    }


@tool
def get_company_info(ticker: str | None = "") -> dict:
    """
    Fetch company name, sector, industry, market cap, and basic fundamental metrics.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        A dict with company info, timestamp, and status.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    valid, clean_ticker = _validate_ticker(ticker)
    if not valid:
        return {
            "ticker": str(ticker).strip().upper() if ticker and isinstance(ticker, str) else "",
            "info": {},
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": clean_ticker,
        }

    success, data = _fetch_alpha_vantage(
        function="OVERVIEW",
        extra_params={"symbol": clean_ticker},
    )
    if not success:
        return {
            "ticker": clean_ticker,
            "info": {},
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": data.get("error", f"Failed to fetch company info for {clean_ticker}"),
        }

    if not data or not isinstance(data, dict) or not any(k in data for k in ["Symbol", "Name"]):
        return {
            "ticker": clean_ticker,
            "info": {},
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": f"No company info found for ticker: {clean_ticker}",
        }

    name = _safe_str(data.get("Name")) or clean_ticker
    sector = _safe_str(data.get("Sector")) or "N/A"
    industry = _safe_str(data.get("Industry")) or "N/A"
    country = _safe_str(data.get("Country")) or "N/A"
    market_cap = _safe_int(data.get("MarketCapitalization"))
    pe_ratio = _safe_float_raw(data.get("TrailingPE") or data.get("PERatio"))
    forward_pe = _safe_float_raw(data.get("ForwardPE"))
    dividend_yield = _safe_float_raw(data.get("DividendYield"))
    fifty_two_week_high = _safe_float(data.get("52WeekHigh"))
    fifty_two_week_low = _safe_float(data.get("52WeekLow"))
    currency = _safe_str(data.get("Currency")) or "USD"

    company_data = {
        "ticker": clean_ticker,
        "name": name,
        "sector": sector,
        "industry": industry,
        "country": country,
        "market_cap": market_cap,
        "pe_ratio": pe_ratio,
        "forward_pe": forward_pe,
        "dividend_yield": dividend_yield,
        "fifty_two_week_high": fifty_two_week_high,
        "fifty_two_week_low": fifty_two_week_low,
        "currency": currency,
        "timestamp": timestamp,
        "notice": DATA_DELAY_NOTICE,
        "status": "success",
    }
    return company_data


@tool
def get_financial_summary(ticker: str | None = "") -> dict:
    """
    Retrieve key financial metrics for a company from Alpha Vantage OVERVIEW.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        A dict of financial metrics.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    valid, clean_ticker = _validate_ticker(ticker)
    if not valid:
        return {
            "ticker": str(ticker).strip().upper() if ticker and isinstance(ticker, str) else "",
            "metrics": {},
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": clean_ticker,
        }

    success, data = _fetch_alpha_vantage(
        function="OVERVIEW",
        extra_params={"symbol": clean_ticker},
    )
    if not success:
        return {
            "ticker": clean_ticker,
            "metrics": {},
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": data.get("error", f"Failed to fetch financial summary for {clean_ticker}"),
        }

    metrics = {
        "market_cap": _safe_int(data.get("MarketCapitalization") or data.get("marketCap")),
        "trailing_pe": _safe_float_raw(data.get("TrailingPE") or data.get("PERatio") or data.get("trailingPE")),
        "forward_pe": _safe_float_raw(data.get("ForwardPE") or data.get("forwardPE")),
        "price_to_book": _safe_float_raw(data.get("PriceToBookRatio") or data.get("priceToBook")),
        "profit_margins": _safe_float_raw(data.get("ProfitMargin") or data.get("profitMargins")),
        "return_on_equity": _safe_float_raw(data.get("ReturnOnEquityTTM") or data.get("returnOnEquity")),
        "total_revenue": _safe_int(data.get("RevenueTTM") or data.get("totalRevenue")),
        "revenue_growth": _safe_float_raw(data.get("QuarterlyRevenueGrowthYOY") or data.get("revenueGrowth")),
        "total_debt": _safe_int(data.get("TotalDebt") or data.get("totalDebt")),
        "free_cashflow": _safe_int(data.get("FreeCashflow") or data.get("freeCashflow")),
    }

    if not data or all(v is None for v in metrics.values()):
        return {
            "ticker": clean_ticker,
            "metrics": metrics,
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": f"No financial summary data found for {clean_ticker}",
        }

    return {
        "ticker": clean_ticker,
        "metrics": metrics,
        "timestamp": timestamp,
        "notice": DATA_DELAY_NOTICE,
        "status": "success",
    }


_BULLISH_WORDS = {
    "beat", "beats", "surge", "surges", "rally", "rallies", "gain", "gains",
    "growth", "upgrade", "upgraded", "record", "strong", "bullish", "outperform",
    "profit", "soar", "soars", "rise", "rises", "buy", "boost",
}
_BEARISH_WORDS = {
    "miss", "misses", "drop", "drops", "fall", "falls", "plunge", "plunges",
    "downgrade", "downgraded", "loss", "losses", "weak", "bearish", "cut",
    "cuts", "decline", "declines", "lawsuit", "probe", "sell", "warning", "risk",
}


def _infer_headline_sentiment(title: str) -> str:
    """Infer lightweight sentiment label from a news headline."""
    words = set(re.findall(r"[a-z]+", (title or "").lower()))
    pos = len(words & _BULLISH_WORDS)
    neg = len(words & _BEARISH_WORDS)
    if pos > neg:
        return "Bullish"
    if neg > pos:
        return "Bearish"
    return "Neutral"


def _parse_rss_feed(xml_text: str, default_source: str, limit: int = 8) -> list[dict]:
    """Parse standard RSS 2.0 XML into normalized news article dicts."""
    articles: list[dict] = []
    root = ET.fromstring(xml_text)
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = (source_el.text.strip() if source_el is not None and source_el.text else "") or default_source
        if not title or not url:
            continue
        articles.append(
            {
                "title": title,
                "source": source,
                "url": url,
                "published_at": pub_date,
                "sentiment": _infer_headline_sentiment(title),
            }
        )
    return articles


@tool
def search_stock_news(ticker: str | None = "") -> dict:
    """
    Fetch latest financial news for a stock ticker using free public RSS feeds
    (Yahoo Finance RSS primary, Google News RSS fallback).

    Args:
        ticker: Stock ticker symbol.

    Returns:
        A dict containing normalized news articles, source, timestamp, and status.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    valid, clean_ticker = _validate_ticker(ticker)
    if not valid:
        return {
            "ticker": str(ticker).strip().upper() if ticker and isinstance(ticker, str) else "",
            "news": [],
            "timestamp": timestamp,
            "notice": DATA_DELAY_NOTICE,
            "status": "error",
            "error": clean_ticker,
        }

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StockResearchAgent/1.0)"
    }
    sources = [
        (
            "Yahoo Finance RSS",
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={clean_ticker}&region=US&lang=en-US",
        ),
        (
            "Google News RSS",
            f"https://news.google.com/rss/search?q={clean_ticker}+stock+finance&hl=en-US&gl=US&ceid=US:en",
        ),
    ]

    last_error = "No news articles found."
    for source_name, feed_url in sources:
        try:
            resp = requests.get(feed_url, headers=headers, timeout=10)
            resp.raise_for_status()
            articles = _parse_rss_feed(resp.text, default_source=source_name, limit=8)
            if articles:
                return {
                    "ticker": clean_ticker,
                    "news": articles,
                    "feed_source": source_name,
                    "timestamp": timestamp,
                    "notice": DATA_DELAY_NOTICE,
                    "status": "success",
                }
        except Exception as e:
            logger.warning(f"[{clean_ticker}] {source_name} fetch failed: {e}")
            last_error = str(e)

    return {
        "ticker": clean_ticker,
        "news": [],
        "timestamp": timestamp,
        "notice": DATA_DELAY_NOTICE,
        "status": "unavailable",
        "error": f"Unable to fetch financial news for {clean_ticker}: {last_error}",
    }


# Registry — import this list when building the LangGraph agent
STOCK_TOOLS = [
    get_stock_price,
    get_stock_history,
    get_company_info,
    get_financial_summary,
    search_stock_news,
]
