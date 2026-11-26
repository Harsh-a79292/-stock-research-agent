"""
services/pdf_service.py
───────────────────────
Professional PDF Equity Research Report generator using ReportLab.
Converts LangGraph agent research results into clean, printable PDF documents.
"""

import html
import io
import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _safe_str(val, default="—") -> str:
    """Convert value to string safely."""
    if val is None or str(val).strip() in ("", "None", "null", "N/A", "nan"):
        return default
    return str(val).strip()


def _safe_curr(val, default="—") -> str:
    """Format currency safely."""
    try:
        if val is None:
            return default
        f = float(val)
        return f"${f:,.2f}"
    except (TypeError, ValueError):
        return default


def _safe_large_num(val, default="—") -> str:
    """Format large numbers in T/B/M."""
    try:
        if val is None:
            return default
        f = float(val)
        if f >= 1e12:
            return f"${f / 1e12:.2f}T"
        elif f >= 1e9:
            return f"${f / 1e9:.2f}B"
        elif f >= 1e6:
            return f"${f / 1e6:.2f}M"
        return f"${f:,.0f}"
    except (TypeError, ValueError):
        return default


def _safe_ratio(val, default="—") -> str:
    """Format multiplier ratio safely."""
    try:
        if val is None:
            return default
        f = float(val)
        return f"{f:.2f}x"
    except (TypeError, ValueError):
        return default


def _safe_pct(val, default="—") -> str:
    """Format percentage safely."""
    try:
        if val is None:
            return default
        f = float(val)
        return f"{f:.2%}"
    except (TypeError, ValueError):
        return default


def _parse_markdown_to_flowables(text: str, styles: dict) -> list:
    """
    Convert markdown lines into styled ReportLab flowables.
    Handles headings (#, ##, ###), bold (**text**), italics (*text*),
    blockquotes (>), bullet points, and code blocks.
    """
    flowables = []
    if not text:
        return flowables

    lines = text.strip().split("\n")
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flowables.append(Spacer(1, 4))
            continue

        # Horizontal rule
        if line in ("---", "***", "___"):
            flowables.append(Spacer(1, 4))
            flowables.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=6))
            continue

        # Heading 1
        if line.startswith("# "):
            content = html.escape(line[2:].strip())
            content = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", content)
            flowables.append(Spacer(1, 8))
            flowables.append(Paragraph(content, styles["ReportH1"]))
            continue

        # Heading 2
        if line.startswith("## "):
            content = html.escape(line[3:].strip())
            content = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", content)
            flowables.append(Spacer(1, 6))
            flowables.append(Paragraph(content, styles["ReportH2"]))
            continue

        # Heading 3
        if line.startswith("### "):
            content = html.escape(line[4:].strip())
            content = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", content)
            flowables.append(Spacer(1, 4))
            flowables.append(Paragraph(content, styles["ReportH3"]))
            continue

        # Blockquote
        if line.startswith("> "):
            content = html.escape(line[2:].strip())
            content = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", content)
            content = re.sub(r"\*(.*?)\*", r"<i>\1</i>", content)
            flowables.append(Paragraph(f"<i>{content}</i>", styles["ReportQuote"]))
            continue

        # Bullet point
        if line.startswith(("- ", "* ", "• ")):
            content = html.escape(line[2:].strip())
            content = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", content)
            content = re.sub(r"\*(.*?)\*", r"<i>\1</i>", content)
            flowables.append(Paragraph(f"&bull; &nbsp; {content}", styles["ReportBullet"]))
            continue

        # Standard Paragraph
        content = html.escape(line)
        content = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", content)
        content = re.sub(r"\*(.*?)\*", r"<i>\1</i>", content)
        content = re.sub(r"`(.*?)`", r"<font name='Courier'>\1</font>", content)
        flowables.append(Paragraph(content, styles["ReportBody"]))

    return flowables


def generate_pdf_report(state: dict, output_path: str | Path | None = None) -> bytes:
    """
    Generate a complete, professionally formatted PDF research report from AgentState.

    Args:
        state: The LangGraph AgentState dictionary containing ticker, query, intent,
               tool_results, and analysis.
        output_path: Optional file path to write the PDF to.

    Returns:
        bytes: Raw PDF document bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    # Base Styles
    base_styles = getSampleStyleSheet()

    styles = {
        "DocTitle": ParagraphStyle(
            "DocTitle",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
            alignment=0,
            spaceAfter=4,
        ),
        "DocSubtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=12,
        ),
        "ReportH1": ParagraphStyle(
            "ReportH1",
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=8,
            spaceAfter=4,
        ),
        "ReportH2": ParagraphStyle(
            "ReportH2",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#e11d48"),
            spaceBefore=6,
            spaceAfter=3,
        ),
        "ReportH3": ParagraphStyle(
            "ReportH3",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=4,
            spaceAfter=2,
        ),
        "ReportBody": ParagraphStyle(
            "ReportBody",
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#334155"),
            spaceAfter=4,
        ),
        "ReportBullet": ParagraphStyle(
            "ReportBullet",
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#334155"),
            leftIndent=12,
            spaceAfter=2,
        ),
        "ReportQuote": ParagraphStyle(
            "ReportQuote",
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#475569"),
            leftIndent=15,
            spaceAfter=4,
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1e293b"),
        ),
        "TableCellBold": ParagraphStyle(
            "TableCellBold",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#0f172a"),
        ),
        "Disclaimer": ParagraphStyle(
            "Disclaimer",
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#94a3b8"),
            alignment=1,
            spaceBefore=10,
        ),
    }

    elements = []

    # 1. Header Banner
    ticker = _safe_str(state.get("ticker"), "UNKNOWN").upper()
    query = _safe_str(state.get("query"), "Stock Analysis")
    intent = _safe_str(state.get("intent"), "Research").upper().replace("_", " ")
    timestamp_str = datetime.now().strftime("%B %d, %Y - %H:%M UTC")

    tool_results = state.get("tool_results", {})
    if not isinstance(tool_results, dict):
        tool_results = {}

    price_res = tool_results.get("price", {}) if isinstance(tool_results.get("price"), dict) else {}
    company_res = tool_results.get("company_info", {}) if isinstance(tool_results.get("company_info"), dict) else {}
    fin_res = tool_results.get("financial_summary", {}) if isinstance(tool_results.get("financial_summary"), dict) else {}
    metrics = fin_res.get("metrics", {}) if isinstance(fin_res.get("metrics"), dict) else {}

    company_name = _safe_str(company_res.get("name"), ticker)

    # Title & Metadata
    elements.append(Paragraph(f"EQUITY RESEARCH REPORT: {ticker}", styles["DocTitle"]))
    elements.append(Paragraph(f"<b>Company:</b> {company_name} | <b>Query:</b> \"{html.escape(query)}\" | <b>Intent:</b> {intent} | <b>Generated:</b> {timestamp_str}", styles["DocSubtitle"]))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#e11d48"), spaceAfter=8))

    # 2. Executive Key Metrics Table
    curr_price = _safe_curr(price_res.get("price"))
    prev_close = _safe_curr(price_res.get("previous_close"))
    chg = price_res.get("change")
    pct = price_res.get("change_percent")
    if chg is not None and pct is not None:
        sign = "+" if chg > 0 else ""
        chg_display = f"{sign}{chg:.2f} ({sign}{pct:.2f}%)"
    else:
        chg_display = "—"

    market_cap = _safe_large_num(metrics.get("market_cap") or company_res.get("market_cap"))
    pe_ratio = _safe_ratio(metrics.get("trailing_pe") or company_res.get("pe_ratio"))
    fwd_pe = _safe_ratio(metrics.get("forward_pe"))
    sector = _safe_str(company_res.get("sector"))
    industry = _safe_str(company_res.get("industry"))
    revenue = _safe_large_num(metrics.get("total_revenue"))
    margin = _safe_pct(metrics.get("profit_margins"))

    metrics_table_data = [
        [
            Paragraph("<b>Market Price</b>", styles["TableCellBold"]),
            Paragraph(curr_price, styles["TableCell"]),
            Paragraph("<b>Day Change</b>", styles["TableCellBold"]),
            Paragraph(chg_display, styles["TableCell"]),
            Paragraph("<b>Prev Close</b>", styles["TableCellBold"]),
            Paragraph(prev_close, styles["TableCell"]),
        ],
        [
            Paragraph("<b>Market Cap</b>", styles["TableCellBold"]),
            Paragraph(market_cap, styles["TableCell"]),
            Paragraph("<b>Trailing P/E</b>", styles["TableCellBold"]),
            Paragraph(pe_ratio, styles["TableCell"]),
            Paragraph("<b>Forward P/E</b>", styles["TableCellBold"]),
            Paragraph(fwd_pe, styles["TableCell"]),
        ],
        [
            Paragraph("<b>Sector</b>", styles["TableCellBold"]),
            Paragraph(sector, styles["TableCell"]),
            Paragraph("<b>Revenue (TTM)</b>", styles["TableCellBold"]),
            Paragraph(revenue, styles["TableCell"]),
            Paragraph("<b>Profit Margin</b>", styles["TableCellBold"]),
            Paragraph(margin, styles["TableCell"]),
        ],
    ]

    col_widths = [85, 90, 85, 95, 85, 100]
    t = Table(metrics_table_data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(t)
    elements.append(Spacer(1, 10))

    # 3. AI Research Synthesis Section
    analysis_text = state.get("analysis", "")
    if analysis_text:
        analysis_flowables = _parse_markdown_to_flowables(analysis_text, styles)
        elements.extend(analysis_flowables)
    else:
        elements.append(Paragraph("<i>No detailed analysis was generated for this query.</i>", styles["ReportBody"]))

    # 4. Disclaimer Footer
    elements.append(Spacer(1, 12))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=4))
    disclaimer_text = (
        "CONFIDENTIAL & AUTOMATED — This document is an automated equity research report compiled by the AI Stock Research Agent. "
        "Market data provided via Alpha&nbsp;Vantage and is not guaranteed real-time. For informational purposes only; does not constitute investment advice."
    )
    elements.append(Paragraph(disclaimer_text, styles["Disclaimer"]))

    # Build Document
    doc.build(elements)

    pdf_bytes = buffer.getvalue()
    buffer.close()

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes
