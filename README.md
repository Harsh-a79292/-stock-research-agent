# AI Stock Research & Automation Agent

An end-to-end AI equity research assistant powered by **LangGraph**, **Google Gemini**, **Alpha Vantage**, **Yahoo Finance / Google News RSS**, **ReportLab PDF**, **Gmail OAuth 2.0**, **Supabase**, **FastAPI**, and **Streamlit**.

## Architecture

- **Agent Pipeline (`backend/agent/graph.py`)**: LangGraph state machine (`parse_query` -> `fetch_data` -> `analyse`) with selective tool execution (`price_check`, `fundamentals`, `full_research`) and deterministic fallbacks.
- **Market Data & News (`backend/tools/stock_tools.py`)**:
  - Alpha Vantage for live quotes, company overview, financial metrics, and historical OHLCV data.
  - Free RSS feeds (Yahoo Finance RSS primary, Google News RSS fallback) for latest financial news and sentiment.
- **AI Synthesis (`backend/services/gemini_service.py`)**: Uses `google-genai` for query parsing, news summarization, and equity research report generation with 15s HTTP timeout and deterministic fallback.
- **Persistence (`backend/db/supabase_client.py`, `supabase/schema.sql`)**: Stores `research_reports` and atomic `daily_email_deliveries` in Supabase with RLS enabled (`service_role` access only).
- **PDF & Email (`backend/services/pdf_service.py`, `backend/services/gmail_service.py`)**: Generates institutional-style PDF reports and sends them via Gmail OAuth 2.0.
- **API & UI (`backend/main.py`, `frontend/app.py`)**: FastAPI REST backend (`/health`, `/agent/run`, `/reports`, `/reports/{id}`, `/reports/{id}/pdf`) and Streamlit dashboard.
- **Daily Automation (`backend/scripts/daily_research.py`, `.github/workflows/daily_research.yml`)**: Scheduled GitHub Actions workflow (9:00 AM IST / 03:30 UTC daily) with Supabase-backed atomic duplicate prevention.

## Local Setup

1. **Create and activate Python 3.10.11 virtual environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Configure environment variables**:
   - Copy `.env.example` to `.env` and fill in your API keys (never commit `.env`).
3. **Initialize Supabase schema**:
   - Execute `supabase/schema.sql` in your Supabase SQL Editor.
4. **Run FastAPI backend**:
   ```powershell
   .\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
   ```
   - Swagger UI: `http://127.0.0.1:8000/docs`
5. **Run Streamlit frontend**:
   ```powershell
   .\venv\Scripts\python.exe -m streamlit run frontend/app.py
   ```
   - Dashboard: `http://localhost:8501`

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key | Yes (falls back to deterministic mode if missing) |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage API key | Yes |
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_KEY` | Supabase `sb_secret_` / `service_role` key | Yes |
| `GMAIL_CREDENTIALS_FILE` | Path to OAuth Desktop client JSON | For email delivery |
| `GMAIL_TOKEN_FILE` | Path to OAuth token JSON | For email delivery |
| `GMAIL_SENDER_EMAIL` | Sender Gmail address | Optional |
| `DAILY_RESEARCH_TICKERS` | Comma-separated tickers (e.g. `AAPL,MSFT,NVDA`) | For daily script |
| `DAILY_RESEARCH_RECIPIENT` | Recipient email address | For daily script |
| `APP_ENV` | `development` or `production` | Yes |
| `CORS_ORIGINS` | Comma-separated allowed origins in production | For production API |
| `BACKEND_URL` | FastAPI base URL | Optional |

## GitHub Actions Secrets (Daily Automation)

Configure these under **GitHub Repository -> Settings -> Secrets and variables -> Actions -> Repository secrets**:
- `GEMINI_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `GMAIL_SENDER_EMAIL`
- `GMAIL_CREDENTIALS_JSON` (contents of `credentials/gmail_credentials.json`)
- `GMAIL_TOKEN_JSON` (contents of `credentials/gmail_token.json`)
- `DAILY_RESEARCH_TICKERS`
- `DAILY_RESEARCH_RECIPIENT`

## Deployment

### 1. FastAPI Backend on Render
1. Connect your GitHub repository to **Render** using the included `render.yaml` Blueprint (or create a Web Service manually):
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/health`
2. Set the secret environment variables in Render Dashboard (`GEMINI_API_KEY`, `ALPHA_VANTAGE_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`).
3. Set `APP_ENV=production` and `CORS_ORIGINS=https://<your-streamlit-app>.streamlit.app`.

### 2. Streamlit Frontend on Streamlit Community Cloud
1. Go to **share.streamlit.io** and deploy from your GitHub repository:
   - **Main file path**: `frontend/app.py`
   - **Python version**: `3.10`
2. In **App Settings -> Secrets**, configure:
   ```toml
   GEMINI_API_KEY = "..."
   ALPHA_VANTAGE_API_KEY = "..."
   SUPABASE_URL = "..."
   SUPABASE_KEY = "..."
   BACKEND_URL = "https://<your-render-service>.onrender.com"
   ```
3. Update `CORS_ORIGINS` on Render with your live Streamlit Community Cloud URL.
