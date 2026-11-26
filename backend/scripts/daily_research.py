"""
backend/scripts/daily_research.py
─────────────────────────────────
Automated daily stock research & email delivery script.
Reuses LangGraph agent, Alpha Vantage (via agent), Supabase persistence,
ReportLab PDF generation, and Gmail OAuth 2.0 delivery.
"""

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from backend.agent.graph import agent_graph
from backend.core.config import settings
from backend.db.supabase_client import (
    claim_daily_email_delivery,
    release_daily_email_claim,
    save_research_report,
    update_daily_email_delivery,
)
from backend.services.gmail_service import send_research_email, validate_email
from backend.services.pdf_service import generate_pdf_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_tickers(raw_tickers: str | None) -> list[str]:
    """Parse and deduplicate comma-separated stock tickers, preserving order."""
    if not raw_tickers:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in raw_tickers.split(","):
        ticker = item.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            result.append(ticker)
    return result


def run_daily_research(
    tickers: list[str] | None = None,
    recipient: str | None = None,
    force_resend: bool = False,
) -> dict[str, Any]:
    """
    Execute daily stock research for configured tickers, save to Supabase,
    generate PDFs, and email them via Gmail without crashing on individual failures.
    Duplicate prevention is persisted in Supabase (run_date + ticker + recipient).
    """
    resolved_tickers = tickers if tickers is not None else parse_tickers(
        os.getenv("DAILY_RESEARCH_TICKERS", "")
    )
    resolved_recipient = (
        recipient if recipient is not None else os.getenv("DAILY_RESEARCH_RECIPIENT", "")
    ).strip()

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary: dict[str, Any] = {
        "date": run_date,
        "recipient": resolved_recipient,
        "processed": [],
        "skipped": [],
        "failed": [],
    }

    if not resolved_tickers:
        logger.error("No tickers configured in DAILY_RESEARCH_TICKERS.")
        summary["error"] = "No tickers configured."
        return summary

    valid_email, clean_recipient_or_err = validate_email(resolved_recipient)
    if not valid_email:
        logger.error(f"Invalid DAILY_RESEARCH_RECIPIENT: {clean_recipient_or_err}")
        summary["error"] = clean_recipient_or_err
        return summary

    for ticker in resolved_tickers:
        try:
            logger.info(f"[{ticker}] Running LangGraph research agent...")
            query = f"Comprehensive daily stock research report for {ticker}"
            state = agent_graph.invoke({"query": query})

            if not isinstance(state, dict) or state.get("error") or not (state.get("analysis") or "").strip():
                err_msg = (state or {}).get("error") or "Empty analysis returned by agent."
                logger.warning(f"[{ticker}] Research failed: {err_msg}")
                summary["failed"].append({"ticker": ticker, "stage": "agent", "error": err_msg})
                continue

            save_res = save_research_report(state)
            saved_report_id = (
                save_res.get("report", {}).get("id")
                if save_res.get("status") == "success" and isinstance(save_res.get("report"), dict)
                else None
            )
            if save_res.get("status") != "success":
                logger.warning(f"[{ticker}] Supabase save warning: {save_res.get('error')}")

            pdf_bytes = generate_pdf_report(state)
            if not pdf_bytes:
                logger.warning(f"[{ticker}] PDF generation returned empty bytes.")
                summary["failed"].append({"ticker": ticker, "stage": "pdf", "error": "Empty PDF"})
                continue

            if not force_resend and not claim_daily_email_delivery(
                run_date=run_date,
                ticker=ticker,
                recipient=clean_recipient_or_err,
                report_id=saved_report_id,
            ):
                logger.info(f"[{ticker}] Already claimed/delivered today ({run_date}); skipping duplicate.")
                summary["skipped"].append({"ticker": ticker, "reason": "already_sent_today"})
                continue

            subject = f"Daily Stock Research Report: {ticker} ({run_date})"
            body = (
                f"Hello,\n\n"
                f"Please find attached the automated daily stock research report for {ticker} ({run_date}).\n\n"
                f"Disclaimer: Market data is provided via Alpha Vantage for informational purposes only.\n\n"
                f"Best regards,\nAI Stock Research Agent"
            )
            pdf_filename = f"{ticker}_daily_research_{run_date}.pdf"

            email_res = send_research_email(
                recipient=clean_recipient_or_err,
                subject=subject,
                body=body,
                pdf_bytes=pdf_bytes,
                pdf_filename=pdf_filename,
                interactive_auth=False,
            )

            if email_res.get("status") == "success":
                message_id = email_res.get("message_id")
                logger.info(f"[{ticker}] Email delivered (message_id={message_id}).")
                update_daily_email_delivery(
                    run_date=run_date,
                    ticker=ticker,
                    recipient=clean_recipient_or_err,
                    message_id=message_id,
                )
                summary["processed"].append(
                    {
                        "ticker": ticker,
                        "message_id": message_id,
                        "saved_report_id": saved_report_id,
                    }
                )
            else:
                if not force_resend:
                    release_daily_email_claim(run_date, ticker, clean_recipient_or_err)
                err_msg = email_res.get("error", "Unknown Gmail error")
                logger.warning(f"[{ticker}] Email delivery failed: {err_msg}")
                summary["failed"].append({"ticker": ticker, "stage": "email", "error": err_msg})

        except Exception as e:
            logger.exception(f"[{ticker}] Unexpected error during daily research: {e}")
            summary["failed"].append({"ticker": ticker, "stage": "unexpected", "error": str(e)})

    return summary


if __name__ == "__main__":
    _ = settings.app_env
    result = run_daily_research(
        force_resend=os.getenv("DAILY_RESEARCH_FORCE_RESEND", "").lower() == "true"
    )
    logger.info(
        f"Daily research finished: processed={len(result['processed'])}, "
        f"skipped={len(result['skipped'])}, failed={len(result['failed'])}"
    )
    if result.get("error"):
        sys.exit(1)
    sys.exit(0)
