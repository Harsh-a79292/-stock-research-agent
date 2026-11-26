"""
db/supabase_client.py
─────────────────────
Initialises and exposes the Supabase client and persistence helpers for
saving and retrieving stock research reports.
"""

import json
import logging
from typing import Any

from supabase import Client, create_client

from backend.core.config import settings

logger = logging.getLogger(__name__)

TABLE_NAME = "research_reports"


def _create_supabase_client() -> Client | None:
    """Create and return the Supabase client using env-based credentials."""
    url = (settings.supabase_url or "").strip()
    key = (settings.supabase_key or "").strip()
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        logger.warning(f"Failed to initialize Supabase client: {type(e).__name__}")
        return None


# Shared client — may be None if credentials are not configured
supabase: Client | None = _create_supabase_client()


def _get_client() -> Client | None:
    """Return active Supabase client or attempt lazy creation."""
    global supabase
    if supabase is None:
        supabase = _create_supabase_client()
    return supabase


def _json_safe(data: Any) -> Any:
    """Ensure nested dict/list values are JSON-serializable for JSONB columns."""
    if data is None:
        return None
    try:
        return json.loads(json.dumps(data, default=str))
    except Exception:
        return None


def _is_successful_research(state: dict) -> tuple[bool, str]:
    """Verify that the agent state represents a completed, non-failed research run."""
    if not isinstance(state, dict):
        return False, "Invalid research state."
    if state.get("error"):
        return False, "Research run ended with an error."
    ticker = (state.get("ticker") or "").strip()
    if not ticker:
        return False, "Missing stock ticker."
    analysis = (state.get("analysis") or "").strip()
    if not analysis:
        return False, "Missing analysis output."

    tool_results = state.get("tool_results")
    if isinstance(tool_results, dict) and tool_results:
        statuses = [
            v.get("status")
            for v in tool_results.values()
            if isinstance(v, dict) and "status" in v
        ]
        if statuses and all(s == "error" for s in statuses):
            return False, "All market data tool calls failed."

    return True, ""


def save_research_report(state: dict) -> dict:
    """
    Persist a completed research report to Supabase `research_reports`.
    Failed research runs are never saved.
    """
    ok, reason = _is_successful_research(state)
    if not ok:
        return {"status": "skipped", "error": reason}

    client = _get_client()
    if client is None:
        return {"status": "error", "error": "Supabase client is not configured."}

    tool_results = state.get("tool_results") or {}
    if not isinstance(tool_results, dict):
        tool_results = {}

    payload = {
        "ticker": str(state.get("ticker", "")).strip().upper(),
        "query": str(state.get("query") or "").strip(),
        "intent": str(state.get("intent") or "full_research").strip(),
        "status": "success",
        "analysis": str(state.get("analysis") or ""),
        "stock_data": _json_safe(tool_results.get("price")),
        "company_info": _json_safe(tool_results.get("company_info")),
        "financial_summary": _json_safe(tool_results.get("financial_summary")),
        "history": _json_safe(tool_results.get("history")),
        "news": _json_safe(tool_results.get("news")),
    }

    try:
        response = client.table(TABLE_NAME).insert(payload).execute()
        rows = getattr(response, "data", None) or []
        saved_row = rows[0] if rows else payload
        return {"status": "success", "report": saved_row}
    except Exception as e:
        logger.error(f"Supabase save_research_report error: {type(e).__name__}: {e}")
        return {"status": "error", "error": f"Database error saving report: {type(e).__name__}"}


def get_recent_reports(limit: int = 20) -> dict:
    """
    Fetch the most recent saved research reports ordered by created_at descending.
    """
    client = _get_client()
    if client is None:
        return {"status": "error", "reports": [], "error": "Supabase client is not configured."}

    safe_limit = max(1, min(int(limit or 20), 100))
    try:
        response = (
            client.table(TABLE_NAME)
            .select("id, ticker, query, intent, status, created_at")
            .order("created_at", desc=True)
            .limit(safe_limit)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        return {"status": "success", "reports": rows}
    except Exception as e:
        logger.error(f"Supabase get_recent_reports error: {type(e).__name__}: {e}")
        return {"status": "error", "reports": [], "error": f"Database error fetching reports: {type(e).__name__}"}


def get_report_by_id(report_id: str) -> dict:
    """
    Fetch a single saved research report by its UUID.
    """
    if not report_id or not isinstance(report_id, str) or not report_id.strip():
        return {"status": "error", "report": None, "error": "Invalid report ID."}

    client = _get_client()
    if client is None:
        return {"status": "error", "report": None, "error": "Supabase client is not configured."}

    try:
        response = (
            client.table(TABLE_NAME)
            .select("*")
            .eq("id", report_id.strip())
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        if not rows:
            return {"status": "error", "report": None, "error": f"Report not found: {report_id}"}
        return {"status": "success", "report": rows[0]}
    except Exception as e:
        logger.error(f"Supabase get_report_by_id error: {type(e).__name__}: {e}")
        return {"status": "error", "report": None, "error": f"Database error fetching report: {type(e).__name__}"}


def report_to_agent_state(report: dict) -> dict:
    """
    Convert a stored `research_reports` row back into an AgentState dict for UI rendering.
    """
    if not isinstance(report, dict):
        return {}
    tool_results = {}
    if report.get("stock_data") is not None:
        tool_results["price"] = report.get("stock_data")
    if report.get("company_info") is not None:
        tool_results["company_info"] = report.get("company_info")
    if report.get("financial_summary") is not None:
        tool_results["financial_summary"] = report.get("financial_summary")
    if report.get("history") is not None:
        tool_results["history"] = report.get("history")
    if report.get("news") is not None:
        tool_results["news"] = report.get("news")

    return {
        "query": report.get("query") or "",
        "ticker": report.get("ticker") or "",
        "intent": report.get("intent") or "full_research",
        "analysis": report.get("analysis") or "",
        "tool_results": tool_results,
        "error": None,
        "saved_report_id": report.get("id"),
        "saved_created_at": report.get("created_at"),
    }


def claim_daily_email_delivery(
    run_date: str,
    ticker: str,
    recipient: str,
    report_id: str | None = None,
) -> bool:
    """
    Atomically claim (run_date, ticker, recipient) via INSERT before sending email.
    Returns True if this run claimed the slot, False if already claimed/sent.
    """
    client = get_supabase_client()
    if client is None:
        return False
    try:
        payload = {
            "run_date": run_date,
            "ticker": ticker.upper(),
            "recipient": recipient.lower(),
            "report_id": report_id,
        }
        client.table("daily_email_deliveries").insert(payload).execute()
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "23505" in err_str or "duplicate key" in err_str or "unique" in err_str:
            return False
        logger.warning(f"Failed to claim daily_email_deliveries: {e}")
        return False


def update_daily_email_delivery(
    run_date: str,
    ticker: str,
    recipient: str,
    message_id: str | None = None,
) -> None:
    """Update message_id on an already-claimed delivery record."""
    client = get_supabase_client()
    if client is None or not message_id:
        return
    try:
        (
            client.table("daily_email_deliveries")
            .update({"message_id": message_id})
            .eq("run_date", run_date)
            .eq("ticker", ticker.upper())
            .eq("recipient", recipient.lower())
            .execute()
        )
    except Exception as e:
        logger.warning(f"Failed to update daily_email_deliveries: {e}")


def release_daily_email_claim(run_date: str, ticker: str, recipient: str) -> None:
    """Release a claimed slot if email delivery failed so a retry can proceed."""
    client = get_supabase_client()
    if client is None:
        return
    try:
        (
            client.table("daily_email_deliveries")
            .delete()
            .eq("run_date", run_date)
            .eq("ticker", ticker.upper())
            .eq("recipient", recipient.lower())
            .execute()
        )
    except Exception as e:
        logger.warning(f"Failed to release daily_email_deliveries claim: {e}")
