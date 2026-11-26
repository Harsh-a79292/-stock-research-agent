"""
services/gemini_service.py
──────────────────────────
Google Gemini service using the modern google-genai SDK.
Handles query parsing (extracting ticker & intent) and synthesis
of stock research reports, with deterministic fallbacks.
"""

import json
import logging
import re
from google import genai
from google.genai import types
from backend.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.8-flash"

KNOWN_COMPANIES = {
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "TESLA": "TSLA",
    "META": "META",
    "FACEBOOK": "META",
    "NVIDIA": "NVDA",
    "IBM": "IBM",
    "NETFLIX": "NFLX",
    "INTEL": "INTC",
    "AMD": "AMD",
    "ORACLE": "ORCL",
    "SALESFORCE": "CRM",
    "BERKSHIRE": "BRK.B",
    "JPMORGAN": "JPM",
    "DISNEY": "DIS",
    "COCA-COLA": "KO",
    "COKE": "KO",
    "PEPSI": "PEP",
    "WALMART": "WMT",
}


def get_gemini_client() -> genai.Client | None:
    """Return an authenticated genai.Client instance or None if no API key is set."""
    api_key = settings.gemini_api_key.strip() if settings.gemini_api_key else ""
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=15_000))
    except Exception as e:
        logger.error(f"Failed to initialize Gemini Client: {e}")
        return None


def fallback_parse_query(query: str) -> dict:
    """
    Deterministic rule-based parser for ticker and intent.
    Used when Gemini API is unavailable, unconfigured, or quota is exhausted.
    """
    if not query or not isinstance(query, str):
        return {"ticker": None, "intent": "price_check"}

    clean_query = query.strip()
    upper_query = clean_query.upper()

    # 1. Match against known company names
    found_ticker = None
    for company, sym in KNOWN_COMPANIES.items():
        if re.search(r"\b" + re.escape(company) + r"\b", upper_query):
            found_ticker = sym
            break

    # 2. Check for explicit cashtag ($AAPL) or isolated uppercase symbol
    if not found_ticker:
        cashtags = re.findall(r"\$([A-Za-z]{1,5})\b", clean_query)
        if cashtags:
            found_ticker = cashtags[0].upper()
        else:
            common_stopwords = {
                "A", "I", "AN", "THE", "IS", "ARE", "FOR", "AND", "OR", "IN",
                "ON", "AT", "TO", "OF", "IT", "WHAT", "HOW", "WHY", "CAN", "YOU",
                "ME", "MY", "BUY", "SELL", "GET", "SHOW", "NOW", "TODAY", "WEEK",
                "YEAR", "STOCK", "SHARE", "PRICE", "NEWS", "REPORT", "DATA",
            }
            tokens = re.findall(r"\b[A-Za-z]{1,5}\b", clean_query)
            for t in tokens:
                if t.isupper() and t not in common_stopwords:
                    found_ticker = t
                    break

    # 3. Classify intent
    lower = clean_query.lower()
    fundamental_keywords = [
        "p/e", "pe ratio", "market cap", "valuation", "fundamentals",
        "revenue", "debt", "profit", "margin", "balance sheet", "book value",
        "financial", "earnings", "ratio",
    ]
    research_keywords = [
        "research", "analyze", "analysis", "report", "deep dive",
        "recommendation", "forecast", "outlook", "prospect", "full",
        "trend", "history", "compare",
    ]
    price_keywords = [
        "price", "quote", "cost", "how much", "trading at", "share price",
        "stock price", "close", "change",
    ]

    if any(kw in lower for kw in research_keywords):
        intent = "full_research"
    elif any(kw in lower for kw in fundamental_keywords):
        intent = "fundamentals"
    elif any(kw in lower for kw in price_keywords):
        intent = "price_check"
    else:
        intent = "full_research" if found_ticker else "price_check"

    return {"ticker": found_ticker, "intent": intent}


def parse_query_with_gemini(query: str) -> dict:
    """
    Extract stock ticker and user intent using Gemini.
    Falls back gracefully to deterministic rule-based parsing if Gemini fails.
    """
    client = get_gemini_client()
    if not client:
        logger.info("Gemini client not configured. Using deterministic query parser.")
        return fallback_parse_query(query)

    prompt = (
        "You are a financial query analyzer. Analyze the following user stock research query:\n"
        f"Query: \"{query}\"\n\n"
        "Instructions:\n"
        "1. Extract the stock ticker symbol (e.g., AAPL, MSFT, IBM, TSLA). If a company name is mentioned, "
        "convert it to its standard ticker symbol. If no stock or company is mentioned, return null for ticker.\n"
        "2. Classify intent into exactly one of:\n"
        "   - 'price_check': User only wants current price, quote, or today's price change.\n"
        "   - 'fundamentals': User wants company overview, valuation metrics, P/E ratio, market cap, or financial summary.\n"
        "   - 'full_research': User wants comprehensive research, historical trend, news, analysis, or general company evaluation.\n\n"
        "Respond strictly with a JSON object in this format (no markdown, no backticks):\n"
        "{\"ticker\": \"TICKER_OR_NULL\", \"intent\": \"price_check|fundamentals|full_research\"}"
    )

    try:
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt,
        )
        text = response.text.strip() if response and response.text else ""
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text.strip())

        ticker = parsed.get("ticker")
        if ticker and isinstance(ticker, str):
            clean_ticker = ticker.strip().upper()
            ticker = None if clean_ticker in ("NULL", "NONE", "") else clean_ticker
        else:
            ticker = None

        intent = parsed.get("intent", "price_check")
        if intent not in ("price_check", "fundamentals", "full_research"):
            intent = "price_check"

        return {"ticker": ticker, "intent": intent}
    except Exception as e:
        logger.warning(f"Gemini query parsing failed ({e}). Falling back to rule-based parser.")
        return fallback_parse_query(query)


def generate_deterministic_report(query: str, ticker: str, intent: str, tool_results: dict) -> str:
    """
    Generate a structured markdown research report directly from tool results.
    Guarantees a clean, non-empty response if Gemini is unavailable or quota is exhausted.
    """
    lines = []
    lines.append(f"# Stock Research Report: {ticker.upper()}")
    lines.append(f"**Query**: *\"{query}\"* | **Intent**: `{intent}`\n")

    price_data = tool_results.get("price")
    if isinstance(price_data, dict) and price_data.get("status") == "success":
        lines.append("## Price & Market Summary")
        lines.append(f"- **Current Price**: ${price_data.get('price'):,.2f}")
        lines.append(f"- **Previous Close**: ${price_data.get('previous_close'):,.2f}")
        chg = price_data.get("change")
        pct = price_data.get("change_percent")
        chg_sign = "+" if (chg and chg > 0) else ""
        lines.append(f"- **Change**: {chg_sign}{chg} ({chg_sign}{pct}%)")
        lines.append(f"- **Timestamp**: {price_data.get('timestamp')}\n")
    elif isinstance(price_data, dict) and price_data.get("status") == "error":
        lines.append("## Price & Market Summary")
        lines.append(f"> Price data error: {price_data.get('error')}\n")

    info_data = tool_results.get("company_info")
    if isinstance(info_data, dict) and info_data.get("status") == "success":
        lines.append("## Company Overview")
        lines.append(f"- **Company Name**: {info_data.get('name')}")
        lines.append(f"- **Sector**: {info_data.get('sector')}")
        lines.append(f"- **Industry**: {info_data.get('industry')}")
        lines.append(f"- **Country**: {info_data.get('country')}")
        if info_data.get("fifty_two_week_high") is not None:
            lines.append(
                f"- **52-Week Range**: ${info_data.get('fifty_two_week_low')} - ${info_data.get('fifty_two_week_high')}"
            )
        lines.append("")

    fin_data = tool_results.get("financial_summary")
    if isinstance(fin_data, dict) and fin_data.get("status") == "success":
        m = fin_data.get("metrics", {})
        lines.append("## Key Financial Metrics")
        if m.get("market_cap") is not None:
            lines.append(f"- **Market Cap**: ${m.get('market_cap'):,}")
        if m.get("trailing_pe") is not None:
            lines.append(f"- **Trailing P/E**: {m.get('trailing_pe')}")
        if m.get("forward_pe") is not None:
            lines.append(f"- **Forward P/E**: {m.get('forward_pe')}")
        if m.get("price_to_book") is not None:
            lines.append(f"- **Price to Book**: {m.get('price_to_book')}")
        if m.get("profit_margins") is not None:
            lines.append(f"- **Profit Margin**: {m.get('profit_margins'):.2%}")
        if m.get("return_on_equity") is not None:
            lines.append(f"- **Return on Equity**: {m.get('return_on_equity'):.2%}")
        if m.get("total_revenue") is not None:
            lines.append(f"- **Total Revenue**: ${m.get('total_revenue'):,}")
        if m.get("revenue_growth") is not None:
            lines.append(f"- **Revenue Growth (YoY)**: {m.get('revenue_growth'):.2%}")
        lines.append("")

    hist_data = tool_results.get("history")
    if isinstance(hist_data, dict) and hist_data.get("status") == "success":
        records = hist_data.get("history", [])
        if records:
            lines.append("## Historical Price Range")
            lines.append(f"- **Period**: {hist_data.get('period', '1mo')}")
            lines.append(f"- **Trading Sessions**: {len(records)}")
            lines.append(f"- **Range**: {records[0]['date']} to {records[-1]['date']}\n")

    news_data = tool_results.get("news")
    if isinstance(news_data, dict):
        if news_data.get("status") == "unavailable":
            lines.append("## News & Sentiment")
            lines.append(f"> Note: {news_data.get('error', 'Stock news is unavailable.')}\n")
        elif news_data.get("status") == "success" and news_data.get("news"):
            lines.append("## Recent Financial News")
            if news_data.get("summary"):
                lines.append(news_data["summary"])
                lines.append("")
            for item in news_data.get("news", [])[:5]:
                title = item.get("title", "Untitled")
                url = item.get("url") or item.get("link") or ""
                source = item.get("source") or item.get("publisher") or "News"
                sentiment = item.get("sentiment", "Neutral")
                pub_date = item.get("published_at") or ""
                date_suffix = f" · {pub_date}" if pub_date else ""
                link_part = f"[{title}]({url})" if url else title
                lines.append(f"- {link_part} ({source}{date_suffix}) — **{sentiment}**")
            lines.append("")

    lines.append("---")
    lines.append("*Report generated using deterministic market analysis engine.*")
    return "\n".join(lines)


def generate_stock_analysis(query: str, ticker: str, intent: str, tool_results: dict) -> str:
    """
    Synthesize tool results into a structured stock research report using Gemini.
    Falls back to deterministic report generation if Gemini fails or is unconfigured.
    """
    client = get_gemini_client()
    if not client:
        logger.info("Gemini client not configured. Using deterministic report generator.")
        return generate_deterministic_report(query, ticker, intent, tool_results)

    tools_json = json.dumps(tool_results, indent=2, default=str)

    prompt = (
        "You are an expert AI Stock Research Analyst. Your goal is to provide a structured, professional, "
        "and insightful research report answering the user's query based on the provided market data.\n\n"
        f"User Query: \"{query}\"\n"
        f"Ticker: {ticker}\n"
        f"Research Intent: {intent}\n\n"
        f"Market Data:\n{tools_json}\n\n"
        "Guidelines:\n"
        "1. Format with clean Markdown headings (`#`, `##`, bullet points, bold numbers).\n"
        "2. Address the user's query directly in an Executive Summary.\n"
        "3. Highlight price action, valuation metrics, and fundamental drivers.\n"
        "4. Do NOT hallucinate metrics that are null, None, or marked as unavailable.\n"
        "5. Be concise, objective, and analytical."
    )

    try:
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt,
        )
        if response and response.text:
            return response.text.strip()
        return generate_deterministic_report(query, ticker, intent, tool_results)
    except Exception as e:
        logger.warning(f"Gemini report generation failed ({e}). Falling back to deterministic report.")
        return generate_deterministic_report(query, ticker, intent, tool_results)


def summarize_stock_news(ticker: str, articles: list[dict]) -> str:
    """
    Generate a concise Gemini-powered summary of recent financial news articles,
    falling back deterministically if Gemini is unavailable.
    """
    if not articles:
        return ""

    top_articles = articles[:6]
    client = get_gemini_client()
    if client:
        bullets = "\n".join(
            f"- {a.get('title', '')} (Source: {a.get('source', 'News')}, "
            f"Date: {a.get('published_at', 'N/A')}, Sentiment: {a.get('sentiment', 'Neutral')})"
            for a in top_articles
        )
        prompt = (
            f"Summarize the latest financial news for {ticker} in 2-3 concise sentences "
            f"covering key catalysts, risks, and overall sentiment based strictly on these headlines:\n\n"
            f"{bullets}"
        )
        try:
            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=prompt,
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            logger.warning(f"Gemini news summary failed ({e}); using deterministic summary.")

    # Deterministic fallback summary
    sentiments = [a.get("sentiment", "Neutral") for a in top_articles]
    bullish = sentiments.count("Bullish")
    bearish = sentiments.count("Bearish")
    overall = "Bullish" if bullish > bearish else "Bearish" if bearish > bullish else "Neutral"
    headlines = "; ".join(a.get("title", "") for a in top_articles[:3] if a.get("title"))
    return (
        f"Recent coverage for {ticker} reflects an overall **{overall}** tone "
        f"across {len(top_articles)} articles. Key headlines: {headlines}."
    )
