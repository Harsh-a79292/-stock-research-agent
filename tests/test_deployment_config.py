"""
tests/test_deployment_config.py
───────────────────────────────
Focused tests for Task 10 Phase 1: CORS configuration, render.yaml, and README.md.
"""

from pathlib import Path
import yaml

from backend.main import LOCAL_DEV_ORIGINS, get_allowed_origins


def test_cors_preserves_local_dev_origins():
    origins = get_allowed_origins(cors_origins="", app_env="development")
    for expected in LOCAL_DEV_ORIGINS:
        assert expected in origins


def test_cors_production_origins_from_env():
    origins = get_allowed_origins(
        cors_origins="https://stock-agent.streamlit.app/, https://custom.example.com",
        app_env="production",
    )
    assert origins == [
        "https://stock-agent.streamlit.app",
        "https://custom.example.com",
    ]


def test_render_yaml_valid_and_secret_free():
    render_path = Path("render.yaml")
    assert render_path.is_file()
    data = yaml.safe_load(render_path.read_text(encoding="utf-8"))
    service = data["services"][0]
    assert service["type"] == "web"
    assert "uvicorn backend.main:app" in service["startCommand"]
    assert service["healthCheckPath"] == "/health"
    for var in service["envVars"]:
        if var["key"] in {"GEMINI_API_KEY", "ALPHA_VANTAGE_API_KEY", "SUPABASE_URL", "SUPABASE_KEY", "CORS_ORIGINS"}:
            assert var.get("sync") is False


def test_readme_documents_deployment_targets():
    readme = Path("README.md").read_text(encoding="utf-8")
    for section in ("Render", "Streamlit Community Cloud", "Supabase", "GitHub Actions", "CORS_ORIGINS"):
        assert section in readme
