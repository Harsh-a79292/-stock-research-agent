"""
services/gmail_service.py
─────────────────────────
Gmail API OAuth 2.0 integration for sending stock research PDF reports.
Requests only the minimum required scope (gmail.send) and never logs or
exposes OAuth tokens or client secrets.
"""

import base64
import json
import logging
import re
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.core.config import settings

logger = logging.getLogger(__name__)

# Minimum necessary permission: send-only access
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_email(email: str) -> tuple[bool, str]:
    """
    Validate recipient email address format and guard against header injection.

    Returns:
        (is_valid, clean_email_or_error_message)
    """
    if not isinstance(email, str):
        return False, "Recipient email must be a string."
    if "\r" in email or "\n" in email:
        return False, "Invalid email address: newline characters are not allowed."
    clean = email.strip()
    if not clean:
        return False, "Recipient email address cannot be empty."
    if not EMAIL_REGEX.match(clean):
        return False, f"Invalid email address format: {clean}"
    return True, clean


def _get_paths() -> tuple[Path, Path]:
    """Return configured credentials and token paths."""
    creds_path = Path(settings.gmail_credentials_file)
    token_path = Path(settings.gmail_token_file)
    return creds_path, token_path


def _has_valid_client_secrets(creds_path: Path) -> bool:
    """Return True if creds_path exists and contains a valid OAuth client JSON structure."""
    if not creds_path.is_file() or creds_path.stat().st_size == 0:
        return False
    try:
        data = json.loads(creds_path.read_text(encoding="utf-8"))
        return isinstance(data, dict) and ("installed" in data or "web" in data)
    except Exception:
        return False


def get_gmail_status() -> dict:
    """
    Non-interactive status check for UI display.
    Never triggers OAuth browser flow or sends emails.
    """
    creds_path, token_path = _get_paths()
    has_creds_file = _has_valid_client_secrets(creds_path)
    has_token_file = token_path.is_file()

    if has_token_file:
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            if creds and (creds.valid or (creds.expired and creds.refresh_token)):
                return {
                    "ready": True,
                    "authenticated": True,
                    "credentials_present": has_creds_file,
                    "status_label": "Gmail Ready",
                }
        except Exception:
            pass

    if has_creds_file:
        return {
            "ready": True,
            "authenticated": False,
            "credentials_present": True,
            "status_label": "Gmail OAuth Ready",
        }

    return {
        "ready": False,
        "authenticated": False,
        "credentials_present": False,
        "status_label": "Gmail Setup Needed",
    }


def _save_token(token_path: Path, creds: Credentials) -> None:
    """Persist OAuth token JSON securely without logging token contents."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as token_file:
        token_file.write(creds.to_json())


def get_gmail_credentials(interactive: bool = False) -> tuple[Credentials | None, str | None]:
    """
    Load, refresh, or (if interactive=True) obtain Gmail OAuth 2.0 credentials.

    Returns:
        (Credentials_or_None, error_message_or_None)
    """
    creds_path, token_path = _get_paths()
    creds: Credentials | None = None

    if token_path.is_file():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            logger.warning("Failed to load existing Gmail token file; re-authentication required.")
            creds = None

    if creds and creds.valid:
        return creds, None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(token_path, creds)
            return creds, None
        except RefreshError:
            logger.warning("Gmail OAuth token refresh failed or was revoked.")
            creds = None
        except Exception as e:
            logger.warning(f"Unexpected error refreshing Gmail token: {type(e).__name__}")
            creds = None

    if not interactive:
        return None, "Gmail authentication required. Please authorize Gmail OAuth 2.0."

    if not creds_path.is_file():
        return (
            None,
            f"Gmail OAuth credentials file not found at '{creds_path}'. "
            "Download your OAuth 2.0 Client ID JSON from Google Cloud Console and save it there.",
        )

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        creds = flow.run_local_server(port=0)
        _save_token(token_path, creds)
        return creds, None
    except Exception as e:
        logger.error(f"Gmail OAuth flow failed: {type(e).__name__}")
        return None, f"Gmail OAuth authentication failed: {e}"


def build_default_email_body(state: dict) -> str:
    """
    Generate a professional email body summarizing the stock research report.
    """
    ticker = (state.get("ticker") or "STOCK").upper()
    query = state.get("query") or f"Research on {ticker}"
    tool_results = state.get("tool_results") or {}
    price_res = tool_results.get("price", {}) if isinstance(tool_results, dict) else {}
    company_res = tool_results.get("company_info", {}) if isinstance(tool_results, dict) else {}

    company_name = company_res.get("name") or ticker
    price = price_res.get("price")
    change = price_res.get("change")
    change_pct = price_res.get("change_percent")

    lines = [
        "Hello,",
        "",
        f"Please find attached the Equity Research Report (PDF) for {company_name} ({ticker}).",
        "",
        f"Research Query: {query}",
    ]

    if price is not None:
        price_line = f"Latest Price: ${float(price):,.2f}"
        if change is not None and change_pct is not None:
            sign = "+" if float(change) > 0 else ""
            price_line += f" ({sign}{float(change):.2f}, {sign}{float(change_pct):.2f}%)"
        lines.append(price_line)

    analysis = (state.get("analysis") or "").strip()
    if analysis:
        # Include a concise plain-text preview without markdown clutter
        clean_lines = [
            ln.lstrip("#>*- ").strip()
            for ln in analysis.splitlines()
            if ln.strip() and not ln.strip().startswith("---")
        ]
        summary_excerpt = " ".join(clean_lines[:5])
        if len(summary_excerpt) > 450:
            summary_excerpt = summary_excerpt[:447].rstrip() + "..."
        if summary_excerpt:
            lines.extend(["", "Report Highlights:", summary_excerpt])

    lines.extend(
        [
            "",
            "Disclaimer: Market data is provided via Alpha Vantage for informational purposes only and does not constitute financial advice.",
            "",
            "Best regards,",
            "AI Stock Research Agent",
        ]
    )
    return "\n".join(lines)


def build_email_message(
    recipient: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    sender: str = "",
) -> dict:
    """
    Construct a MIME multipart email with a PDF attachment encoded for the Gmail API.
    """
    msg = MIMEMultipart()
    msg["To"] = recipient
    msg["Subject"] = subject.replace("\r", " ").replace("\n", " ").strip()
    if sender and sender.strip():
        msg["From"] = sender.strip()

    msg.attach(MIMEText(body, "plain", "utf-8"))

    safe_filename = Path(pdf_filename).name or "stock_research_report.pdf"
    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename=safe_filename)
    msg.attach(attachment)

    raw_bytes = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return {"raw": raw_bytes}


def send_research_email(
    recipient: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    interactive_auth: bool = True,
) -> dict:
    """
    Send the generated PDF stock research report via the Gmail API.
    Must only be invoked after explicit user confirmation.

    Returns:
        dict with 'status' ('success' or 'error'), plus 'message_id' or 'error'.
    """
    valid_email, clean_recipient_or_err = validate_email(recipient)
    if not valid_email:
        return {"status": "error", "error": clean_recipient_or_err}

    clean_subject = (subject or "").strip()
    if not clean_subject:
        return {"status": "error", "error": "Email subject cannot be empty."}

    clean_body = (body or "").strip()
    if not clean_body:
        return {"status": "error", "error": "Email body cannot be empty."}

    if not pdf_bytes or not isinstance(pdf_bytes, (bytes, bytearray)):
        return {"status": "error", "error": "PDF report attachment is missing or empty."}

    creds, auth_error = get_gmail_credentials(interactive=interactive_auth)
    if auth_error or not creds:
        return {"status": "error", "error": auth_error or "Gmail authentication failed."}

    try:
        raw_message = build_email_message(
            recipient=clean_recipient_or_err,
            subject=clean_subject,
            body=clean_body,
            pdf_bytes=bytes(pdf_bytes),
            pdf_filename=pdf_filename,
            sender=settings.gmail_sender_email,
        )
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        sent = service.users().messages().send(userId="me", body=raw_message).execute()
        message_id = sent.get("id", "")
        logger.info(f"Research report email sent successfully (message_id={message_id}).")
        return {
            "status": "success",
            "message_id": message_id,
            "recipient": clean_recipient_or_err,
            "filename": Path(pdf_filename).name,
        }
    except HttpError as e:
        logger.error(f"Gmail API HttpError (status={getattr(e.resp, 'status', 'unknown')}): {e}")
        return {
            "status": "error",
            "error": f"Gmail API error (HTTP {getattr(e.resp, 'status', 'unknown')}): Unable to send email.",
        }
    except RefreshError:
        return {
            "status": "error",
            "error": "Gmail OAuth token expired or was revoked. Please re-authenticate.",
        }
    except Exception as e:
        logger.error(f"Failed to send email via Gmail API: {type(e).__name__}: {e}")
        return {
            "status": "error",
            "error": f"Failed to send email: {e}",
        }
