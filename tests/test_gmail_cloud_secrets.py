"""
tests/test_gmail_cloud_secrets.py
─────────────────────────────────
Focused tests for Gmail OAuth authentication across both paths:
1. Local file-based authentication (gmail_credentials.json + gmail_token.json).
2. Streamlit Secrets authentication (GMAIL_CREDENTIALS_JSON + GMAIL_TOKEN_JSON).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.core.config import settings
from backend.services.gmail_service import get_gmail_credentials, get_gmail_status


SAMPLE_CLIENT_JSON = {
    "installed": {
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-client-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

SAMPLE_TOKEN_JSON = {
    "token": "ya29.mock-access-token",
    "refresh_token": "1//0mock-refresh-token",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "test-client-id.apps.googleusercontent.com",
    "client_secret": "test-client-secret",
    "scopes": ["https://www.googleapis.com/auth/gmail.send"],
}


def test_gmail_auth_local_file_path(tmp_path: Path, monkeypatch):
    creds_file = tmp_path / "gmail_credentials.json"
    token_file = tmp_path / "gmail_token.json"
    creds_file.write_text(json.dumps(SAMPLE_CLIENT_JSON), encoding="utf-8")
    token_file.write_text(json.dumps(SAMPLE_TOKEN_JSON), encoding="utf-8")

    monkeypatch.setattr(settings, "gmail_credentials_file", str(creds_file))
    monkeypatch.setattr(settings, "gmail_token_file", str(token_file))

    mock_creds = MagicMock(valid=True, expired=False, refresh_token="1//0mock-refresh-token")
    with patch("backend.services.gmail_service.Credentials.from_authorized_user_file", return_value=mock_creds):
        status = get_gmail_status()
        assert status["ready"] is True
        assert status["authenticated"] is True
        assert status["credentials_present"] is True

        creds, err = get_gmail_credentials(interactive=False)
        assert err is None
        assert creds is mock_creds


def test_gmail_auth_streamlit_secrets_path(tmp_path: Path, monkeypatch):
    # Ensure local files do NOT exist (simulates Streamlit Community Cloud)
    monkeypatch.setattr(settings, "gmail_credentials_file", str(tmp_path / "missing_creds.json"))
    monkeypatch.setattr(settings, "gmail_token_file", str(tmp_path / "missing_token.json"))
    monkeypatch.delenv("GMAIL_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("GMAIL_TOKEN_JSON", raising=False)

    fake_secrets = {
        "GMAIL_CREDENTIALS_JSON": json.dumps(SAMPLE_CLIENT_JSON),
        "GMAIL_TOKEN_JSON": json.dumps(SAMPLE_TOKEN_JSON),
    }
    mock_creds = MagicMock(valid=True, expired=False, refresh_token="1//0mock-refresh-token")

    with (
        patch("backend.services.gmail_service._get_streamlit_secret", side_effect=lambda k: fake_secrets.get(k)),
        patch("backend.services.gmail_service.Credentials.from_authorized_user_info", return_value=mock_creds) as mock_info,
    ):
        status = get_gmail_status()
        assert status["ready"] is True
        assert status["authenticated"] is True
        assert status["credentials_present"] is True
        assert status["status_label"] == "Gmail Ready"

        creds, err = get_gmail_credentials(interactive=False)
        assert err is None
        assert creds is mock_creds
        assert mock_info.call_count >= 1
