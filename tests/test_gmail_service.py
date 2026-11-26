"""
tests/test_gmail_service.py
───────────────────────────
Unit tests for Task 5: Gmail API OAuth 2.0 integration service.
Uses mocked Google OAuth credentials and mocked Gmail API responses.
"""

import base64
from email import message_from_bytes
from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from backend.core.config import settings
from backend.services.gmail_service import (
    SCOPES,
    build_default_email_body,
    build_email_message,
    get_gmail_credentials,
    get_gmail_status,
    send_research_email,
    validate_email,
)


def test_validate_email_valid_and_invalid():
    """Verify email validation accepts valid addresses and rejects invalid/injected ones."""
    ok, clean = validate_email("  analyst@example.com  ")
    assert ok is True
    assert clean == "analyst@example.com"

    for bad in ["", "   ", "not-an-email", "user@", "@domain.com", "a@b.com\nBcc:evil@x.com", None]:
        ok, err = validate_email(bad)
        assert ok is False
        assert isinstance(err, str) and len(err) > 0


def test_build_default_email_body():
    """Verify default email body includes ticker, company name, price, and highlights."""
    state = {
        "ticker": "IBM",
        "query": "Analyze IBM",
        "tool_results": {
            "price": {"price": 235.62, "change": 2.62, "change_percent": 1.12},
            "company_info": {"name": "International Business Machines"},
        },
        "analysis": "# Executive Summary\nIBM shows steady enterprise AI momentum.",
    }
    body = build_default_email_body(state)
    assert "International Business Machines (IBM)" in body
    assert "$235.62" in body
    assert "+2.62, +1.12%" in body
    assert "IBM shows steady enterprise AI momentum." in body


def test_build_email_message_mime_and_pdf_attachment():
    """Verify MIME construction attaches PDF bytes with correct headers."""
    pdf_bytes = b"%PDF-1.4\n%MockPDFContent"
    payload = build_email_message(
        recipient="analyst@example.com",
        subject="Equity Research Report: AAPL",
        body="Attached is the AAPL report.",
        pdf_bytes=pdf_bytes,
        pdf_filename="AAPL_research_report.pdf",
    )

    assert "raw" in payload
    decoded = base64.urlsafe_b64decode(payload["raw"].encode("utf-8"))
    parsed_msg = message_from_bytes(decoded)

    assert parsed_msg["To"] == "analyst@example.com"
    assert parsed_msg["Subject"] == "Equity Research Report: AAPL"

    parts = parsed_msg.get_payload()
    assert len(parts) == 2
    assert parts[0].get_content_type() == "text/plain"
    assert "Attached is the AAPL report." in parts[0].get_payload(decode=True).decode("utf-8")

    pdf_part = parts[1]
    assert pdf_part.get_content_type() == "application/pdf"
    assert pdf_part.get_filename() == "AAPL_research_report.pdf"
    assert pdf_part.get_payload(decode=True) == pdf_bytes


def test_minimum_scope_requested():
    """Ensure only the minimum send-only Gmail scope is requested."""
    assert SCOPES == ["https://www.googleapis.com/auth/gmail.send"]


def test_get_gmail_status_missing_files(tmp_path):
    """Verify non-interactive status check when no credentials or token exist."""
    orig_creds = settings.gmail_credentials_file
    orig_token = settings.gmail_token_file
    try:
        settings.gmail_credentials_file = str(tmp_path / "missing_creds.json")
        settings.gmail_token_file = str(tmp_path / "missing_token.json")
        status = get_gmail_status()
        assert status["ready"] is False
        assert status["authenticated"] is False
        assert status["credentials_present"] is False
    finally:
        settings.gmail_credentials_file = orig_creds
        settings.gmail_token_file = orig_token


def test_get_gmail_status_empty_credentials_file(tmp_path):
    """Verify 0-byte or invalid credentials JSON is not reported as ready."""
    empty_creds = tmp_path / "empty_creds.json"
    empty_creds.write_text("", encoding="utf-8")

    orig_creds = settings.gmail_credentials_file
    orig_token = settings.gmail_token_file
    try:
        settings.gmail_credentials_file = str(empty_creds)
        settings.gmail_token_file = str(tmp_path / "missing_token.json")
        status = get_gmail_status()
        assert status["ready"] is False
        assert status["credentials_present"] is False
        assert status["status_label"] == "Gmail Setup Needed"
    finally:
        settings.gmail_credentials_file = orig_creds
        settings.gmail_token_file = orig_token


def test_get_gmail_credentials_missing_credentials_file(tmp_path):
    """Verify interactive auth returns clear error when credentials JSON is missing."""
    orig_creds = settings.gmail_credentials_file
    orig_token = settings.gmail_token_file
    try:
        settings.gmail_credentials_file = str(tmp_path / "nonexistent_creds.json")
        settings.gmail_token_file = str(tmp_path / "nonexistent_token.json")
        creds, err = get_gmail_credentials(interactive=True)
        assert creds is None
        assert "not found" in err
    finally:
        settings.gmail_credentials_file = orig_creds
        settings.gmail_token_file = orig_token


def test_get_gmail_credentials_refresh_expired_token(tmp_path):
    """Verify expired token with refresh_token refreshes and persists updated token."""
    token_file = tmp_path / "gmail_token.json"
    token_file.write_text("{}", encoding="utf-8")

    orig_token = settings.gmail_token_file
    try:
        settings.gmail_token_file = str(token_file)
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "mock_refresh_token"
        mock_creds.to_json.return_value = '{"token": "refreshed"}'

        with patch("backend.services.gmail_service.Credentials.from_authorized_user_file", return_value=mock_creds), \
             patch("backend.services.gmail_service.Request"):
            creds, err = get_gmail_credentials(interactive=False)

        assert err is None
        assert creds is mock_creds
        mock_creds.refresh.assert_called_once()
        assert token_file.read_text(encoding="utf-8") == '{"token": "refreshed"}'
    finally:
        settings.gmail_token_file = orig_token


def test_get_gmail_credentials_refresh_error_handled(tmp_path):
    """Verify RefreshError on revoked token is handled gracefully without crashing."""
    token_file = tmp_path / "gmail_token.json"
    token_file.write_text("{}", encoding="utf-8")

    orig_token = settings.gmail_token_file
    try:
        settings.gmail_token_file = str(token_file)
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "revoked_token"
        mock_creds.refresh.side_effect = RefreshError("Token has been expired or revoked.")

        with patch("backend.services.gmail_service.Credentials.from_authorized_user_file", return_value=mock_creds), \
             patch("backend.services.gmail_service.Request"):
            creds, err = get_gmail_credentials(interactive=False)

        assert creds is None
        assert "authentication required" in err.lower()
    finally:
        settings.gmail_token_file = orig_token


def test_send_research_email_validation_blocks_send():
    """Verify invalid email or missing PDF prevents any Gmail API call."""
    with patch("backend.services.gmail_service.build") as mock_build:
        res_bad_email = send_research_email("bad-email", "Subject", "Body", b"%PDF-1.4", "a.pdf")
        assert res_bad_email["status"] == "error"

        res_no_pdf = send_research_email("ok@example.com", "Subject", "Body", b"", "a.pdf")
        assert res_no_pdf["status"] == "error"

        mock_build.assert_not_called()


def test_send_research_email_success():
    """Verify successful Gmail API send returns message_id and does not expose tokens."""
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "msg_12345abc"
    }

    with patch("backend.services.gmail_service.get_gmail_credentials", return_value=(mock_creds, None)), \
         patch("backend.services.gmail_service.build", return_value=mock_service):
        res = send_research_email(
            recipient="investor@example.com",
            subject="Equity Research Report: IBM",
            body="Please find attached the IBM report.",
            pdf_bytes=b"%PDF-1.4\n%Test",
            pdf_filename="IBM_research_report.pdf",
        )

    assert res["status"] == "success"
    assert res["message_id"] == "msg_12345abc"
    assert res["recipient"] == "investor@example.com"
    assert res["filename"] == "IBM_research_report.pdf"
    mock_service.users.return_value.messages.return_value.send.assert_called_once()


def test_send_research_email_http_error():
    """Verify Gmail API HttpError is caught and returned as a structured error."""
    mock_creds = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 403
    mock_resp.reason = "Forbidden"
    http_err = HttpError(resp=mock_resp, content=b'{"error": "Insufficient Permission"}')

    mock_service = MagicMock()
    mock_service.users.return_value.messages.return_value.send.return_value.execute.side_effect = http_err

    with patch("backend.services.gmail_service.get_gmail_credentials", return_value=(mock_creds, None)), \
         patch("backend.services.gmail_service.build", return_value=mock_service):
        res = send_research_email(
            recipient="investor@example.com",
            subject="Equity Research Report: IBM",
            body="Body text",
            pdf_bytes=b"%PDF-1.4\n%Test",
            pdf_filename="IBM_research_report.pdf",
        )

    assert res["status"] == "error"
    assert "403" in res["error"]
