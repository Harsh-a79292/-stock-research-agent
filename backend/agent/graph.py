"""
agent/graph.py
──────────────
LangGraph stock research agent with natural language query parsing,
selective tool execution, and structured report synthesis.
"""

import logging
from typing import TypedDict
from langgraph.graph import StateGraph, END

from backend.services.gemini_service import (
    parse_query_with_gemini,
    generate_stock_analysis,
)
from backend.tools.stock_tools import (
    get_stock_price,
    get_stock_history,
    get_company_info,
    get_financial_summary,
    search_stock_news,
)

logger = logging.getLogger(__name__)


# ── State Schema ──────────────────────────────────────────────────────────────
class AgentState(TypedDict, total=False):
    """Shared state passed between every node in the graph."""
    query: str                  # User's research question
    ticker: str | None          # Extracted stock ticker
    intent: str                 # "price_check" | "fundamentals" | "full_research"
    tool_results: dict          # Raw outputs from tools
    analysis: str               # Final LLM or deterministic analysis
    error: str | None           # Any error message


# ── Node Implementations ──────────────────────────────────────────────────────
def parse_query_node(state: AgentState) -> dict:
    """
    Extract stock ticker and research intent from the user query using Gemini
    or fallback parser.
    """
    query = state.get("query", "")
    if not query or not str(query).strip():
        return {
            "ticker": None,
            "intent": "price_check",
            "error": "Query cannot be empty. Please provide a stock research question or ticker symbol.",
        }

    parsed = parse_query_with_gemini(str(query))
    ticker = parsed.get("ticker")
    intent = parsed.get("intent", "price_check")

    if not ticker:
        return {
            "ticker": None,
            "intent": intent,
            "error": f"Could not identify a valid stock ticker in query: \"{query}\". Please specify a stock symbol (e.g. AAPL, IBM, TSLA).",
        }

    return {
        "ticker": ticker,
        "intent": intent,
        "error": None,
    }


def route_after_parse(state: AgentState) -> str:
    """
    Conditional edge router:
    If ticker extraction failed or an error occurred, route to handle_error.
    Otherwise, proceed to fetch_data.
    """
    if state.get("error") or not state.get("ticker"):
        return "handle_error"
    return "fetch_data"


def handle_error_node(state: AgentState) -> dict:
    """
    Format a clean error response when the query cannot be processed.
    Avoids unnecessary downstream tool or LLM calls.
    """
    err = state.get("error") or "Could not process stock research request."
    analysis = (
        f"# Stock Research Error\n\n"
        f"> **Status**: Unable to complete request\n\n"
        f"{err}\n\n"
        f"**Suggestions**:\n"
        f"- Include a specific ticker symbol (e.g., 'AAPL', 'MSFT', 'TSLA').\n"
        f"- Mention a recognized company name (e.g., 'Apple', 'Microsoft').\n"
        f"- Examples:\n"
        f"  - *'What is Apple's current price?'*\n"
        f"  - *'Financial overview for IBM'*\n"
        f"  - *'Deep dive research report on NVDA'*"
    )
    return {
        "analysis": analysis,
        "error": err,
    }


def fetch_data_node(state: AgentState) -> dict:
    """
    Call stock market tools selectively based on intent to preserve API quota.
    - price_check: only get_stock_price (1 call)
    - fundamentals: get_stock_price, get_company_info, get_financial_summary
    - full_research: all available tools
    """
    ticker = state.get("ticker")
    intent = state.get("intent", "price_check")
    tool_results = {}

    if not ticker:
        return {"tool_results": {}, "error": "No ticker provided for data collection."}

    try:
        if intent == "price_check":
            tool_results["price"] = get_stock_price.invoke({"ticker": ticker})

        elif intent == "fundamentals":
            tool_results["price"] = get_stock_price.invoke({"ticker": ticker})
            tool_results["company_info"] = get_company_info.invoke({"ticker": ticker})
            tool_results["financial_summary"] = get_financial_summary.invoke({"ticker": ticker})

        else:  # full_research
            tool_results["price"] = get_stock_price.invoke({"ticker": ticker})
            tool_results["company_info"] = get_company_info.invoke({"ticker": ticker})
            tool_results["financial_summary"] = get_financial_summary.invoke({"ticker": ticker})
            tool_results["history"] = get_stock_history.invoke({"ticker": ticker, "period": "1mo"})
            tool_results["news"] = search_stock_news.invoke({"ticker": ticker})
    except Exception as e:
        logger.error(f"Error executing stock tools for {ticker}: {e}")
        return {"tool_results": tool_results, "error": f"Tool execution failed: {e}"}

    return {"tool_results": tool_results}


def analyse_node(state: AgentState) -> dict:
    """
    Synthesize tool results into a structured research report using Gemini,
    with deterministic fallback.
    """
    query = state.get("query", "")
    ticker = state.get("ticker", "")
    intent = state.get("intent", "full_research")
    tool_results = state.get("tool_results", {})

    report = generate_stock_analysis(
        query=query,
        ticker=ticker,
        intent=intent,
        tool_results=tool_results,
    )
    return {"analysis": report}


# ── Graph Construction ────────────────────────────────────────────────────────
def build_agent_graph() -> StateGraph:
    """
    Wire nodes into a compiled LangGraph with conditional error routing.

    Returns:
        A compiled StateGraph ready to invoke.
    """
    graph = StateGraph(AgentState)

    graph.add_node("parse_query", parse_query_node)
    graph.add_node("handle_error", handle_error_node)
    graph.add_node("fetch_data", fetch_data_node)
    graph.add_node("analyse", analyse_node)

    graph.set_entry_point("parse_query")

    graph.add_conditional_edges(
        "parse_query",
        route_after_parse,
        {
            "fetch_data": "fetch_data",
            "handle_error": "handle_error",
        },
    )
    graph.add_edge("fetch_data", "analyse")
    graph.add_edge("analyse", END)
    graph.add_edge("handle_error", END)

    return graph.compile()


# Shared compiled graph instance
agent_graph = build_agent_graph()
