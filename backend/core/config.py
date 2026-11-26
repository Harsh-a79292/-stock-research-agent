"""
core/config.py
──────────────
Loads all environment variables from the .env file using pydantic-settings.
Access settings anywhere via:  from backend.core.config import settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Gemini ────────────────────────────────────────────────────────────────
    gemini_api_key: str = ""

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_key: str = ""

    # ── Alpha Vantage ─────────────────────────────────────────────────────────
    alpha_vantage_api_key: str = ""

    # ── Gmail OAuth 2.0 ───────────────────────────────────────────────────────
    gmail_credentials_file: str = "credentials/gmail_credentials.json"
    gmail_token_file: str = "credentials/gmail_token.json"
    gmail_sender_email: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "info"
    cors_origins: str = ""

    # ── Frontend ──────────────────────────────────────────────────────────────
    backend_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Singleton — import this wherever you need config values
settings = Settings()
