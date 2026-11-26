"""
frontend/app.py
───────────────
AI Stock Research & Automation Agent — Streamlit Dashboard.
Directly connects to the Phase 2 LangGraph agent pipeline.
"""

import html
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure workspace root is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from backend.agent.graph import agent_graph
from backend.core.config import settings
from backend.db.supabase_client import (
    get_recent_reports,
    get_report_by_id,
    report_to_agent_state,
    save_research_report,
)
from backend.services.gmail_service import (
    build_default_email_body,
    get_gmail_status,
    send_research_email,
    validate_email,
)
from backend.services.pdf_service import generate_pdf_report

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Research Agent | AI Market Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS: Dark Charcoal & Coral SaaS Theme ──────────────────────────────
st.markdown(
    """
    <style>
    /* Global Reset & Base */
    .stApp {
        background-color: #0d0f15;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    [data-testid="stSidebar"] {
        background-color: #12151f !important;
        border-right: 1px solid rgba(255, 255, 255, 0.07);
    }

    /* Typography */
    h1, h2, h3, h4, h5, h6 {
        color: #f8fafc;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    /* Cards */
    .saas-card {
        background: #161a25;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 20px 24px;
        margin-bottom: 16px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .saas-card:hover {
        border-color: rgba(255, 77, 77, 0.4);
        box-shadow: 0 6px 28px rgba(255, 77, 77, 0.12);
        transform: translateY(-2px);
    }

    /* Metrics Styling */
    .metric-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .metric-label {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #94a3b8;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.85rem;
        font-weight: 800;
        color: #f8fafc;
        letter-spacing: -0.03em;
    }
    .metric-delta-pos {
        color: #10b981;
        font-weight: 600;
        font-size: 0.9rem;
    }
    .metric-delta-neg {
        color: #ff4d4d;
        font-weight: 600;
        font-size: 0.9rem;
    }

    /* Badges */
    .badge-coral {
        background: rgba(255, 77, 77, 0.12);
        color: #ff6b6b;
        border: 1px solid rgba(255, 77, 77, 0.35);
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        display: inline-block;
    }
    .badge-emerald {
        background: rgba(16, 185, 129, 0.12);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.35);
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        display: inline-block;
    }
    .badge-slate {
        background: rgba(148, 163, 184, 0.12);
        color: #cbd5e1;
        border: 1px solid rgba(148, 163, 184, 0.25);
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }

    /* Primary Buttons & Form Submit */
    .stButton>button, div[data-testid="stFormSubmitButton"]>button {
        background: linear-gradient(135deg, #ff4d4d 0%, #e63946 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.55rem 1.4rem !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        box-shadow: 0 4px 16px rgba(230, 57, 70, 0.3) !important;
        transition: all 0.2s ease !important;
    }
    .stButton>button:hover, div[data-testid="stFormSubmitButton"]>button:hover {
        background: linear-gradient(135deg, #ff6666 0%, #ff4d4d 100%) !important;
        box-shadow: 0 6px 24px rgba(255, 77, 77, 0.45) !important;
        transform: translateY(-1px) !important;
    }

    /* Inputs */
    .stTextInput>div>div>input {
        background-color: #161a25 !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        color: #f8fafc !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
        font-size: 1rem !important;
    }
    .stTextInput>div>div>input:focus {
        border-color: #ff4d4d !important;
        box-shadow: 0 0 0 2px rgba(255, 77, 77, 0.25) !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0px 0px;
        padding: 8px 18px;
        color: #94a3b8;
        font-weight: 600;
        background-color: transparent;
    }
    .stTabs [aria-selected="true"] {
        color: #ff6b6b !important;
        border-bottom: 2px solid #ff4d4d !important;
        background-color: rgba(255, 77, 77, 0.05) !important;
    }

    /* Code & Markdown Report */
    .report-box {
        background: #141721;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 24px;
        line-height: 1.65;
        font-size: 0.98rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Formatting Helpers ────────────────────────────────────────────────────────
def format_curr(val: any) -> str:
    """Format currency safely."""
    try:
        if val is None:
            return "N/A"
        f = float(val)
        return f"${f:,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def format_large_num(val: any) -> str:
    """Format large numbers (e.g. market cap, revenue) in T/B/M."""
    try:
        if val is None:
            return "—"
        f = float(val)
        if f >= 1e12:
            return f"${f / 1e12:.2f}T"
        elif f >= 1e9:
            return f"${f / 1e9:.2f}B"
        elif f >= 1e6:
            return f"${f / 1e6:.2f}M"
        return f"${f:,.0f}"
    except (TypeError, ValueError):
        return "—"


def format_ratio(val: any) -> str:
    """Format valuation multiplier ratios safely."""
    try:
        if val is None:
            return "—"
        f = float(val)
        return f"{f:.2f}x"
    except (TypeError, ValueError):
        return "—"


def format_pct(val: any) -> str:
    """Format percentage values safely."""
    try:
        if val is None:
            return "—"
        f = float(val)
        return f"{f:.2%}"
    except (TypeError, ValueError):
        return "—"


# ── Session State Management ──────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state["history"] = []

if "latest_result" not in st.session_state:
    st.session_state["latest_result"] = None

if "result_id" not in st.session_state:
    st.session_state["result_id"] = "init"

if "email_confirm_pending" not in st.session_state:
    st.session_state["email_confirm_pending"] = False

if "email_draft" not in st.session_state:
    st.session_state["email_draft"] = None

if "email_send_result" not in st.session_state:
    st.session_state["email_send_result"] = None

if "sent_email_keys" not in st.session_state:
    st.session_state["sent_email_keys"] = set()


# ── Charting Function ─────────────────────────────────────────────────────────
def build_plotly_chart(history_res: dict, ticker: str) -> go.Figure | None:
    """Build a dark-themed Candlestick + Volume chart from real tool outputs."""
    if not history_res or history_res.get("status") != "success":
        return None

    records = history_res.get("history", [])
    if not records:
        return None

    dates = [r["date"] for r in records]
    opens = [r["open"] for r in records]
    highs = [r["high"] for r in records]
    lows = [r["low"] for r in records]
    closes = [r["close"] for r in records]
    volumes = [r["volume"] for r in records]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.74, 0.26],
    )

    # 1. Candlestick
    fig.add_trace(
        go.Candlestick(
            x=dates,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            name="OHLC",
            increasing_line_color="#10b981",
            increasing_fillcolor="rgba(16, 185, 129, 0.7)",
            decreasing_line_color="#ff4d4d",
            decreasing_fillcolor="rgba(255, 77, 77, 0.7)",
        ),
        row=1,
        col=1,
    )

    # 2. Volume Bar
    vol_colors = [
        "rgba(16, 185, 129, 0.6)" if closes[i] >= opens[i] else "rgba(255, 77, 77, 0.6)"
        for i in range(len(records))
    ]
    fig.add_trace(
        go.Bar(
            x=dates,
            y=volumes,
            name="Volume",
            marker_color=vol_colors,
        ),
        row=2,
        col=1,
    )

    period_label = history_res.get("period", "1mo").upper()
    fig.update_layout(
        title=dict(
            text=f"<b>{ticker.upper()}</b> — Daily OHLCV ({period_label})",
            font=dict(size=15, color="#f1f5f9"),
            x=0.01,
        ),
        template="plotly_dark",
        paper_bgcolor="#161a25",
        plot_bgcolor="#161a25",
        xaxis_rangeslider_visible=False,
        height=470,
        margin=dict(l=40, r=40, t=45, b=25),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="#94a3b8"),
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(255, 255, 255, 0.06)",
            tickfont=dict(color="#94a3b8"),
        ),
        yaxis=dict(
            title=dict(text="Price ($)", font=dict(color="#94a3b8", size=11)),
            showgrid=True,
            gridcolor="rgba(255, 255, 255, 0.06)",
            tickfont=dict(color="#94a3b8"),
        ),
        xaxis2=dict(
            showgrid=True,
            gridcolor="rgba(255, 255, 255, 0.06)",
            tickfont=dict(color="#94a3b8"),
        ),
        yaxis2=dict(
            title=dict(text="Vol", font=dict(color="#94a3b8", size=11)),
            showgrid=False,
            tickfont=dict(color="#94a3b8"),
        ),
    )
    return fig


# ── Execution Trigger ─────────────────────────────────────────────────────────
def execute_research(user_query: str):
    """Run the LangGraph pipeline with the user's natural language question."""
    if not user_query or not user_query.strip():
        st.warning("Please enter a stock query or ticker symbol.")
        return

    with st.spinner("🤖 LangGraph Agent orchestrating tools & Gemini analysis…"):
        try:
            result = agent_graph.invoke({"query": user_query.strip()})
            st.session_state["latest_result"] = result
            st.session_state["result_id"] = f"{result.get('ticker') or 'ERR'}_{int(datetime.now().timestamp() * 1000)}"
            st.session_state["email_confirm_pending"] = False
            st.session_state["email_draft"] = None
            st.session_state["email_send_result"] = None
            st.session_state["db_save_status"] = save_research_report(result)

            # Save to recent query history
            if user_query not in [h["query"] for h in st.session_state["history"]]:
                st.session_state["history"].insert(
                    0,
                    {
                        "query": user_query,
                        "ticker": result.get("ticker") or "N/A",
                        "time": datetime.now().strftime("%H:%M"),
                    },
                )
                if len(st.session_state["history"]) > 6:
                    st.session_state["history"].pop()
        except Exception as e:
            st.error(f"Execution Error: {e}")


# ── Sidebar Navigation & Controls ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚡ **Stock Agent**")
    st.caption("Autonomous Equity Research & Automation")
    st.divider()

    st.markdown("#### **System Connectivity**")
    av_configured = bool(settings.alpha_vantage_api_key)
    gemini_configured = bool(settings.gemini_api_key)

    if av_configured:
        st.markdown('<span class="badge-emerald">● Alpha Vantage Active</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-coral">● Alpha Vantage Missing</span>', unsafe_allow_html=True)

    if gemini_configured:
        st.markdown('<span class="badge-emerald">● Gemini Active</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-coral">● Gemini Offline Engine</span>', unsafe_allow_html=True)

    gmail_status = get_gmail_status()
    if gmail_status.get("ready"):
        st.markdown(f'<span class="badge-emerald">● {gmail_status["status_label"]}</span>', unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="badge-coral">● {gmail_status["status_label"]}</span>', unsafe_allow_html=True)

    st.divider()

    st.markdown("#### **Quick Presets**")
    preset_col1, preset_col2 = st.columns(2)
    with preset_col1:
        if st.button("Apple ($AAPL)", use_container_width=True):
            execute_research("Full research report on Apple AAPL")
        if st.button("IBM Price", use_container_width=True):
            execute_research("What is IBM current stock price?")
    with preset_col2:
        if st.button("Tesla ($TSLA)", use_container_width=True):
            execute_research("Analyze Tesla valuation and financials")
        if st.button("NVIDIA ($NVDA)", use_container_width=True):
            execute_research("Comprehensive deep dive on NVDA")

    st.divider()

    if st.session_state["history"]:
        st.markdown("#### **Recent Inquiries**")
        for item in st.session_state["history"]:
            q_label = f"{item['ticker']}: {item['query'][:22]}…"
            if st.button(q_label, key=f"hist_{item['query']}", use_container_width=True):
                execute_research(item["query"])

    st.divider()

    st.markdown("#### **Research History (DB)**")
    db_res = get_recent_reports(limit=20)
    db_reports = db_res.get("reports", []) if isinstance(db_res, dict) else []
    if db_res.get("status") == "success" and db_reports:
        report_options = {
            f"{r.get('ticker', 'N/A')} | {str(r.get('created_at', ''))[:10]} | {str(r.get('query', ''))[:24]}": r.get("id")
            for r in db_reports
            if r.get("id")
        }
        if report_options:
            selected_label = st.selectbox(
                "Saved Reports (Recent 20)",
                options=list(report_options.keys()),
                key="saved_report_select",
            )
            if st.button("📂 Load Saved Report", key="load_saved_report_btn", use_container_width=True):
                loaded = get_report_by_id(report_options[selected_label])
                if loaded.get("status") == "success" and loaded.get("report"):
                    loaded_state = report_to_agent_state(loaded["report"])
                    st.session_state["latest_result"] = loaded_state
                    st.session_state["result_id"] = f"DB_{loaded['report'].get('id', 'loaded')}"
                    st.session_state["email_confirm_pending"] = False
                    st.session_state["email_draft"] = None
                    st.session_state["email_send_result"] = None
                    st.rerun()
                else:
                    st.error(loaded.get("error", "Could not load saved report."))
    elif db_res.get("status") == "error":
        st.caption("Database history unavailable.")
    else:
        st.caption("No saved reports yet.")

    st.divider()
    st.caption("Engine: LangGraph + Alpha Vantage + Google GenAI")


# ── Main Header & Search Hero ─────────────────────────────────────────────────
st.markdown("## 📈 AI Equity Research Terminal")
st.markdown(
    "<span style='color: #94a3b8;'>Ask any question about a stock in natural language. "
    "The LangGraph agent will automatically extract the ticker, determine your research intent, "
    "execute live Alpha Vantage tools selectively, and generate a synthesized intelligence report.</span>",
    unsafe_allow_html=True,
)
st.write("")

# Search Form (Supports both Enter key and Button click)
with st.form(key="search_form", border=False):
    input_col, btn_col = st.columns([5, 1])
    with input_col:
        query_text = st.text_input(
            "Search Query",
            placeholder="e.g. 'What is IBM trading at?' or 'Give me a full financial report on Apple'",
            label_visibility="collapsed",
            key="main_query_input",
        )
    with btn_col:
        submit_clicked = st.form_submit_button("⚡ Research", use_container_width=True)

    if submit_clicked and query_text:
        execute_research(query_text)

st.write("")


# ── Results Presentation ──────────────────────────────────────────────────────
result = st.session_state.get("latest_result")

if result:
    ticker = result.get("ticker")
    intent = result.get("intent", "price_check")
    error = result.get("error")
    analysis = result.get("analysis", "")
    tool_results = result.get("tool_results", {})

    # 1. Error / Warning Alert Banner
    if error and not ticker:
        st.error(f"**Research Agent Notice:** {error}")
        st.markdown(
            f"""
            <div class="saas-card">
                <h4>⚠️ Query Needs Attention</h4>
                <p>{analysis}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # Header Badge Row
        saved_at = result.get("saved_created_at")
        saved_badge = (
            f'<span class="badge-emerald">SAVED: {str(saved_at)[:10]}</span>'
            if saved_at
            else ""
        )
        badge_html = f"""
        <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 18px; flex-wrap: wrap;">
            <span class="badge-coral">TICKER: {ticker.upper() if ticker else 'UNKNOWN'}</span>
            <span class="badge-slate">INTENT: {intent.upper().replace('_', ' ')}</span>
            <span class="badge-slate">DATA SOURCE: ALPHA VANTAGE</span>
            {saved_badge}
        </div>
        """
        st.markdown(badge_html, unsafe_allow_html=True)

        # 2. Live Key Performance Indicators (KPIs)
        price_res = tool_results.get("price", {}) if isinstance(tool_results, dict) else {}
        company_res = tool_results.get("company_info", {}) if isinstance(tool_results, dict) else {}
        fin_res = tool_results.get("financial_summary", {}) if isinstance(tool_results, dict) else {}
        metrics = fin_res.get("metrics", {}) if isinstance(fin_res, dict) else {}

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)

        with kpi1:
            curr_price = price_res.get("price")
            chg = price_res.get("change")
            pct = price_res.get("change_percent")
            delta_str = ""
            delta_class = "metric-delta-pos"

            if curr_price is not None:
                if chg is not None and pct is not None:
                    chg_sign = "+" if chg > 0 else ""
                    delta_class = "metric-delta-pos" if chg >= 0 else "metric-delta-neg"
                    delta_str = f"{chg_sign}{chg:.2f} ({chg_sign}{pct:.2f}%)"
                val_display = format_curr(curr_price)
            else:
                val_display = "N/A"
                if price_res.get("status") == "error":
                    delta_str = "Price Data Unavailable"
                    delta_class = "metric-delta-neg"

            st.markdown(
                f"""
                <div class="saas-card metric-container">
                    <div class="metric-label">Current Price</div>
                    <div class="metric-value">{val_display}</div>
                    <div class="{delta_class}">{delta_str}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with kpi2:
            prev_close = price_res.get("previous_close")
            prev_val = format_curr(prev_close) if prev_close is not None else "—"
            st.markdown(
                f"""
                <div class="saas-card metric-container">
                    <div class="metric-label">Previous Close</div>
                    <div class="metric-value">{prev_val}</div>
                    <div style="color: #64748b; font-size: 0.85rem;">Prior trading session</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with kpi3:
            market_cap = metrics.get("market_cap") or company_res.get("market_cap")
            cap_str = format_large_num(market_cap)

            st.markdown(
                f"""
                <div class="saas-card metric-container">
                    <div class="metric-label">Market Cap</div>
                    <div class="metric-value">{cap_str}</div>
                    <div style="color: #64748b; font-size: 0.85rem;">Total equity valuation</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with kpi4:
            pe_val = metrics.get("trailing_pe") or company_res.get("pe_ratio")
            pe_str = format_ratio(pe_val)
            sector_name = company_res.get("sector") or "General"
            st.markdown(
                f"""
                <div class="saas-card metric-container">
                    <div class="metric-label">P/E Ratio</div>
                    <div class="metric-value">{pe_str}</div>
                    <div style="color: #64748b; font-size: 0.85rem;">{sector_name}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.write("")

        # 3. Main Dashboard Tabs
        tab_report, tab_chart, tab_company, tab_email, tab_state = st.tabs(
            [
                "📝 Agent Research Report",
                "📊 Interactive OHLCV Chart",
                "🏢 Corporate & Financials",
                "✉️ Email Report",
                "🔍 Debug State",
            ]
        )

        with tab_report:
            rep_col1, rep_col2 = st.columns([4, 1])
            with rep_col1:
                st.markdown("#### **Executive Summary & Strategy**")
            with rep_col2:
                try:
                    pdf_data = generate_pdf_report(result)
                    st.download_button(
                        label="📄 Download PDF",
                        data=pdf_data,
                        file_name=f"{ticker.upper()}_research_report.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.caption("PDF Export unavailable")

            st.markdown(
                f"""
                <div class="saas-card report-box">
                """,
                unsafe_allow_html=True,
            )
            st.markdown(analysis)
            st.markdown("</div>", unsafe_allow_html=True)

        with tab_chart:
            history_res = tool_results.get("history") if isinstance(tool_results, dict) else None
            chart = build_plotly_chart(history_res, ticker)

            if chart:
                st.plotly_chart(chart, use_container_width=True)
                records = history_res.get("history", [])
                if records:
                    with st.expander(f"View {len(records)} Historical OHLCV Records"):
                        st.dataframe(records, use_container_width=True)
            else:
                st.info(
                    f"Historical OHLCV data was not requested for intent **'{intent}'**. "
                    f"To view the interactive price and volume chart, ask for a **'Full research report on {ticker}'** "
                    f"or a historical trend."
                )

        with tab_company:
            comp_col1, comp_col2 = st.columns(2)
            with comp_col1:
                st.markdown("#### **Corporate Profile**")
                name_str = company_res.get("name") or ticker.upper()
                sector_str = company_res.get("sector", "N/A")
                ind_str = company_res.get("industry", "N/A")
                country_str = company_res.get("country", "N/A")
                curr_str = company_res.get("currency", "USD")

                st.markdown(
                    f"""
                    <div class="saas-card">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);"><td style="padding: 8px 0; color: #94a3b8;">Company</td><td style="font-weight: 600; text-align: right;">{name_str}</td></tr>
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);"><td style="padding: 8px 0; color: #94a3b8;">Sector</td><td style="font-weight: 600; text-align: right;">{sector_str}</td></tr>
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);"><td style="padding: 8px 0; color: #94a3b8;">Industry</td><td style="font-weight: 600; text-align: right;">{ind_str}</td></tr>
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);"><td style="padding: 8px 0; color: #94a3b8;">Country</td><td style="font-weight: 600; text-align: right;">{country_str}</td></tr>
                            <tr><td style="padding: 8px 0; color: #94a3b8;">Currency</td><td style="font-weight: 600; text-align: right;">{curr_str}</td></tr>
                        </table>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with comp_col2:
                st.markdown("#### **Financial & Valuation Metrics**")
                f_pe_str = format_ratio(metrics.get("forward_pe"))
                ptb_str = format_ratio(metrics.get("price_to_book"))
                pm_str = format_pct(metrics.get("profit_margins"))
                roe_str = format_pct(metrics.get("return_on_equity"))
                rev_str = format_large_num(metrics.get("total_revenue"))

                st.markdown(
                    f"""
                    <div class="saas-card">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);"><td style="padding: 8px 0; color: #94a3b8;">Forward P/E</td><td style="font-weight: 600; text-align: right;">{f_pe_str}</td></tr>
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);"><td style="padding: 8px 0; color: #94a3b8;">Price to Book</td><td style="font-weight: 600; text-align: right;">{ptb_str}</td></tr>
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);"><td style="padding: 8px 0; color: #94a3b8;">Profit Margin</td><td style="font-weight: 600; text-align: right;">{pm_str}</td></tr>
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.06);"><td style="padding: 8px 0; color: #94a3b8;">Return on Equity</td><td style="font-weight: 600; text-align: right;">{roe_str}</td></tr>
                            <tr><td style="padding: 8px 0; color: #94a3b8;">Total Revenue (TTM)</td><td style="font-weight: 600; text-align: right;">{rev_str}</td></tr>
                        </table>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with tab_email:
            st.markdown("#### **Send Research Report via Gmail**")
            st.caption(
                "Compose your email below. You will be asked to review and explicitly confirm "
                "all details before anything is sent."
            )

            res_id = st.session_state.get("result_id", "init")
            pdf_filename = f"{ticker.upper()}_research_report.pdf"
            try:
                email_pdf_bytes = generate_pdf_report(result)
            except Exception as pdf_err:
                email_pdf_bytes = b""
                st.error(f"Could not generate PDF attachment: {pdf_err}")

            default_subject = f"Equity Research Report: {ticker.upper()}"
            default_body = build_default_email_body(result)

            recipient_input = st.text_input(
                "Recipient Email Address",
                placeholder="e.g. analyst@example.com",
                key=f"email_recipient_{res_id}",
            )
            subject_input = st.text_input(
                "Email Subject",
                value=default_subject,
                key=f"email_subject_{res_id}",
            )
            body_input = st.text_area(
                "Email Body",
                value=default_body,
                height=220,
                key=f"email_body_{res_id}",
            )

            if st.button("👀 Preview & Confirm Email", key=f"preview_email_btn_{res_id}"):
                valid_addr, addr_or_err = validate_email(recipient_input)
                if not valid_addr:
                    st.error(addr_or_err)
                    st.session_state["email_confirm_pending"] = False
                elif not subject_input.strip():
                    st.error("Email subject cannot be empty.")
                    st.session_state["email_confirm_pending"] = False
                elif not body_input.strip():
                    st.error("Email body cannot be empty.")
                    st.session_state["email_confirm_pending"] = False
                elif not email_pdf_bytes:
                    st.error("PDF attachment is unavailable.")
                    st.session_state["email_confirm_pending"] = False
                else:
                    draft_key = f"{res_id}|{addr_or_err}|{subject_input.strip()}|{hash(body_input.strip())}"
                    st.session_state["email_draft"] = {
                        "recipient": addr_or_err,
                        "subject": subject_input.strip(),
                        "body": body_input.strip(),
                        "pdf_filename": pdf_filename,
                        "draft_key": draft_key,
                    }
                    st.session_state["email_confirm_pending"] = True
                    st.session_state["email_send_result"] = None

            # Mandatory User Confirmation Panel
            if st.session_state.get("email_confirm_pending") and st.session_state.get("email_draft"):
                draft = st.session_state["email_draft"]
                already_sent = draft["draft_key"] in st.session_state["sent_email_keys"]

                st.markdown(
                    f"""
                    <div class="saas-card" style="border-color: rgba(255, 77, 77, 0.5);">
                        <h4 style="margin-top: 0;">⚠️ Confirm Email Dispatch</h4>
                        <p><strong>Recipient:</strong> {html.escape(draft['recipient'])}</p>
                        <p><strong>Subject:</strong> {html.escape(draft['subject'])}</p>
                        <p><strong>Attachment:</strong> {html.escape(draft['pdf_filename'])} ({len(email_pdf_bytes):,} bytes)</p>
                        <p><strong>Message Preview:</strong></p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.text(draft["body"])

                conf_col1, conf_col2 = st.columns([2, 1])
                with conf_col1:
                    send_clicked = st.button(
                        "✅ Confirm & Send Email",
                        key=f"confirm_send_btn_{res_id}",
                        disabled=already_sent,
                        use_container_width=True,
                    )
                with conf_col2:
                    if st.button("✖️ Cancel", key=f"cancel_send_btn_{res_id}", use_container_width=True):
                        st.session_state["email_confirm_pending"] = False
                        st.session_state["email_draft"] = None
                        st.rerun()

                if already_sent:
                    st.info("This exact email has already been sent in this session (duplicate send prevented).")
                elif send_clicked:
                    with st.spinner("Sending PDF report via Gmail API…"):
                        send_res = send_research_email(
                            recipient=draft["recipient"],
                            subject=draft["subject"],
                            body=draft["body"],
                            pdf_bytes=email_pdf_bytes,
                            pdf_filename=draft["pdf_filename"],
                            interactive_auth=True,
                        )
                        st.session_state["email_send_result"] = send_res
                        if send_res.get("status") == "success":
                            st.session_state["sent_email_keys"].add(draft["draft_key"])
                            st.session_state["email_confirm_pending"] = False

            send_status = st.session_state.get("email_send_result")
            if isinstance(send_status, dict):
                if send_status.get("status") == "success":
                    st.success(
                        f"Email sent successfully to **{send_status.get('recipient')}** "
                        f"(Message ID: `{send_status.get('message_id')}`)."
                    )
                elif send_status.get("status") == "error":
                    st.error(f"Failed to send email: {send_status.get('error')}")

        with tab_state:
            st.markdown("#### **LangGraph Shared State**")
            st.json(
                {
                    "query": result.get("query"),
                    "ticker": ticker,
                    "intent": intent,
                    "error": error,
                    "tool_results": tool_results,
                }
            )

else:
    # Initial Empty State / Hero Card
    st.markdown(
        """
        <div class="saas-card" style="text-align: center; padding: 48px 24px;">
            <div style="font-size: 2.8rem; margin-bottom: 12px;">📊</div>
            <h3 style="color: #f8fafc; margin-bottom: 8px;">No Research Active</h3>
            <p style="color: #94a3b8; max-width: 520px; margin: 0 auto 20px auto;">
                Type any stock research question in the search bar above or choose a preset in the sidebar to run the LangGraph agent pipeline.
            </p>
            <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
                <span class="badge-slate">Live Alpha Vantage API</span>
                <span class="badge-slate">Gemini 2.5 Planning</span>
                <span class="badge-slate">Automated OHLCV Visuals</span>
                <span class="badge-coral">Zero Fabricated Data</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
