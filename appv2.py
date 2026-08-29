import os
import json
import sqlite3
import textwrap
from datetime import date
from pathlib import Path

import streamlit as st

from graph.workflow import build_rfp_graph


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "data" / "rfp_evaluation.db"

UPLOAD_DIR = BASE_DIR / "rfps" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="RFP Proposal Evaluator",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# SESSION STATE
# =========================================================

if "page" not in st.session_state:
    st.session_state.page = "New Evaluation"

if "current_result" not in st.session_state:
    st.session_state.current_result = None

if "selected_run_id" not in st.session_state:
    st.session_state.selected_run_id = None


# =========================================================
# HTML HELPER
# =========================================================

def html(content):
    """
    Strip all leading/trailing whitespace from every line
    before sending HTML to Streamlit Markdown.

    textwrap.dedent() only removes whitespace that is common
    to every line -- it does NOT flatten indentation of nested
    elements within a multi-level HTML block. Streamlit's
    Markdown renderer treats any line indented 4+ spaces as an
    indented code block, which converts nested HTML into
    visible raw text.

    Stripping every line individually removes that risk
    entirely. Safe here because no HTML in this app relies on
    whitespace being preserved (no <pre> blocks).
    """

    lines = content.strip("\n").split("\n")
    stripped_lines = [line.strip() for line in lines]

    return "\n".join(stripped_lines)


# =========================================================
# PRESENTATION HELPERS
# (cosmetic only -- do not affect data, scoring or routing)
# =========================================================

def score_band(score, max_score):
    """
    Classify a score into a qualitative band purely for
    color-coding in the UI. Does not affect the underlying
    score, ranking or persisted data.
    """

    if not max_score:
        return "neutral", "Not scored"

    pct = score / max_score

    if pct >= 0.75:
        return "strong", "Strong"

    if pct >= 0.5:
        return "moderate", "Moderate"

    return "attention", "Needs attention"


def rank_marker(rank):
    """
    Render rank 1-3 as circled numerals (a small nod to a
    wax-seal / stamped ledger) and everything else as a plain
    ordinal. Purely cosmetic -- the underlying rank value is
    unchanged.
    """

    circled = {1: "①", 2: "②", 3: "③"}

    if rank in circled:
        return circled[rank]

    if rank is None:
        return "—"

    return str(rank)


# =========================================================
# DATABASE
# =========================================================

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_previous_runs():
    """
    Get all completed evaluation runs.
    """

    conn = get_db_connection()

    try:
        rows = conn.execute(
            """
            SELECT
                r.rfp_run_id,
                r.created_at,
                r.status,
                COUNT(s.id) AS supplier_count
            FROM rfp_runs r
            LEFT JOIN supplier_results s
                ON r.rfp_run_id = s.rfp_run_id
            WHERE r.status = 'COMPLETED'
            GROUP BY
                r.rfp_run_id,
                r.created_at,
                r.status
            ORDER BY r.created_at DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


def get_run_results(rfp_run_id):
    """
    Get persisted supplier results for one run.
    """

    conn = get_db_connection()

    try:
        rows = conn.execute(
            """
            SELECT
                id,
                rfp_run_id,
                supplier_name,
                submission_date,
                experience_rating,
                absolute_score,
                ppi,
                final_rank,
                result_json
            FROM supplier_results
            WHERE rfp_run_id = ?
            ORDER BY
                CASE
                    WHEN final_rank IS NULL THEN 999
                    ELSE final_rank
                END,
                supplier_name
            """,
            (rfp_run_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


# =========================================================
# JSON HELPERS
# =========================================================

def parse_json(value):
    if isinstance(value, dict):
        return value

    if not value:
        return {}

    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}

    return {}


def get_ranked_results(state):
    """
    Support both names used by different workflow versions.
    """

    results = state.get("ranked_results", [])

    if not results:
        results = state.get("ranked_suppliers", [])

    return results


# =========================================================
# DESIGN SYSTEM — ENTERPRISE PROCUREMENT UI
# =========================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    :root {
        --bg: #f6f8fb;
        --surface: #ffffff;
        --surface-2: #f9fafc;
        --ink: #172033;
        --muted: #667085;
        --muted-2: #98a2b3;
        --line: #e5e9f0;
        --primary: #3157d5;
        --primary-dark: #2445b3;
        --primary-soft: #eef2ff;
        --success: #138a63;
        --success-soft: #e9f8f2;
        --warning: #b7791f;
        --warning-soft: #fff7e6;
        --danger: #c2413b;
        --danger-soft: #fff0ee;
        --nav: #111827;
        --nav-2: #192235;
        --nav-text: #aeb8ca;
        --shadow-sm: 0 1px 2px rgba(16,24,40,.04);
        --shadow-md: 0 8px 30px rgba(16,24,40,.07);
        --shadow-lg: 0 18px 50px rgba(16,24,40,.10);
        --radius: 16px;
        --radius-sm: 10px;
        --font: "DM Sans", -apple-system, BlinkMacSystemFont, sans-serif;
        --display: "Manrope", -apple-system, BlinkMacSystemFont, sans-serif;
        --mono: "JetBrains Mono", Consolas, monospace;
    }

    html, body, [class*="css"], .stApp {
        font-family: var(--font) !important;
    }

    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"] {
        background: var(--bg) !important;
    }

    [data-testid="stHeader"] {
        height: 0 !important;
    }

    .main .block-container {
        max-width: 1380px !important;
        padding: 2.25rem 3rem 5rem !important;
    }

    h1, h2, h3, h4 {
        font-family: var(--display) !important;
        color: var(--ink) !important;
        letter-spacing: -.025em !important;
    }

    p, label, span, div {
        font-family: var(--font);
    }

    /* ---------------- SIDEBAR ---------------- */

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, var(--nav) 0%, #0d1422 100%) !important;
        border-right: 0 !important;
        min-width: 270px !important;
    }

    [data-testid="stSidebar"] > div:first-child {
        padding: 1.35rem 1.1rem !important;
    }

    [data-testid="stSidebar"] * {
        color: var(--nav-text);
    }

    .brand {
        padding: .4rem .55rem 1.7rem;
        border-bottom: 1px solid rgba(255,255,255,.08);
        margin-bottom: 1.35rem;
    }

    .brand-mark {
        width: 38px;
        height: 38px;
        border-radius: 11px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #4d6eea, #2949bd);
        color: white !important;
        font-weight: 800;
        font-size: 1rem;
        box-shadow: 0 8px 20px rgba(49,87,213,.28);
        vertical-align: middle;
        margin-right: .65rem;
    }

    .brand-name {
        color: #fff !important;
        font-family: var(--display) !important;
        font-weight: 800;
        font-size: 1.08rem;
        vertical-align: middle;
    }

    .brand-sub {
        margin-top: .55rem;
        color: #66738a !important;
        font-family: var(--mono) !important;
        font-size: .61rem;
        letter-spacing: .12em;
        text-transform: uppercase;
    }

    [data-testid="stSidebar"] [data-testid="stRadio"] > div {
        gap: .35rem !important;
    }

    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        border-radius: 10px;
        padding: .72rem .8rem !important;
        transition: all .15s ease;
        font-weight: 600 !important;
        color: #aeb8ca !important;
    }

    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background: rgba(255,255,255,.06);
        color: #fff !important;
    }

    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        background: rgba(77,110,234,.16);
        color: #fff !important;
        box-shadow: inset 3px 0 0 #5b78e7;
    }

    .sidebar-section {
        margin-top: 2rem;
        padding: 1.05rem .8rem 0;
        border-top: 1px solid rgba(255,255,255,.07);
    }

    .sidebar-caption {
        color: #66738a !important;
        font-family: var(--mono) !important;
        font-size: .62rem;
        letter-spacing: .12em;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: .65rem;
    }

    .sidebar-feature {
        color: #aeb8ca !important;
        font-size: .76rem;
        line-height: 2;
    }

    /* ---------------- PAGE HEADER ---------------- */

    .eyebrow {
        color: var(--primary);
        font-family: var(--mono) !important;
        font-size: .67rem;
        font-weight: 600;
        letter-spacing: .13em;
        text-transform: uppercase;
        margin-bottom: .55rem;
    }

    .page-title {
        font-family: var(--display) !important;
        font-size: 2.55rem;
        font-weight: 800;
        color: var(--ink);
        line-height: 1.1;
        margin: 0;
    }

    .page-subtitle {
        color: var(--muted);
        font-size: .98rem;
        max-width: 720px;
        margin-top: .65rem;
        line-height: 1.65;
    }

    .header-rule {
        height: 1px;
        background: linear-gradient(90deg, #cbd5ff 0%, var(--line) 45%, transparent 100%);
        margin: 1.65rem 0 1.9rem;
    }

    .section-head {
        margin: 1.9rem 0 .95rem;
    }

    .section-label {
        color: var(--muted-2);
        font-family: var(--mono) !important;
        font-size: .62rem;
        font-weight: 600;
        letter-spacing: .12em;
        text-transform: uppercase;
    }

    .section-title {
        color: var(--ink);
        font-family: var(--display) !important;
        font-size: 1.28rem;
        font-weight: 800;
        margin-top: .2rem;
    }

    .section-copy {
        color: var(--muted);
        font-size: .84rem;
        margin-top: .2rem;
    }

    /* ---------------- CARDS ---------------- */

    .card {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: 1.45rem 1.55rem;
        box-shadow: var(--shadow-sm);
    }

    .card-title {
        color: var(--ink);
        font-family: var(--display) !important;
        font-weight: 800;
        font-size: 1rem;
    }

    .card-copy {
        color: var(--muted);
        font-size: .82rem;
        line-height: 1.55;
        margin-top: .3rem;
    }

    .upload-intro {
        display: flex;
        align-items: center;
        gap: .8rem;
        margin-bottom: .85rem;
    }

    .upload-icon {
        width: 42px;
        height: 42px;
        border-radius: 12px;
        background: var(--primary-soft);
        color: var(--primary);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.05rem;
        font-weight: 800;
    }

    .doc-card {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 13px;
        padding: .8rem 1rem;
        margin: .55rem 0 .75rem;
        display: flex;
        align-items: center;
        gap: .8rem;
        box-shadow: var(--shadow-sm);
    }

    .doc-number {
        width: 34px;
        height: 34px;
        border-radius: 9px;
        background: var(--primary-soft);
        color: var(--primary);
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: var(--mono) !important;
        font-size: .68rem;
        font-weight: 600;
    }

    .doc-name {
        color: var(--ink);
        font-size: .83rem;
        font-weight: 700;
        word-break: break-word;
    }

    .doc-meta {
        color: var(--muted-2);
        font-size: .69rem;
        margin-top: .1rem;
    }

    /* ---------------- UPLOADER ---------------- */

    [data-testid="stFileUploader"] {
        margin-top: .65rem;
    }

    [data-testid="stFileUploader"] section {
        background: linear-gradient(180deg, #fbfcff 0%, #f7f9fd 100%) !important;
        border: 1.5px dashed #b9c5e8 !important;
        border-radius: 14px !important;
        min-height: 145px;
        padding: 1.1rem !important;
    }

    [data-testid="stFileUploader"] section:hover {
        border-color: var(--primary) !important;
        background: #f8faff !important;
    }

    [data-testid="stFileUploader"] button {
        background: #fff !important;
        color: var(--ink) !important;
        border: 1px solid #d5dbe6 !important;
        border-radius: 9px !important;
        font-weight: 700 !important;
    }

    [data-testid="stFileUploader"] small {
        color: var(--muted-2) !important;
    }

    /* ---------------- INPUTS ---------------- */

    [data-testid="stTextInput"] label,
    [data-testid="stNumberInput"] label,
    [data-testid="stDateInput"] label,
    [data-testid="stSelectbox"] label {
        color: #475467 !important;
        font-size: .73rem !important;
        font-weight: 700 !important;
        margin-bottom: .25rem !important;
    }

    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input {
        background: #fff !important;
        color: var(--ink) !important;
        border: 1px solid #d8dee8 !important;
        border-radius: 9px !important;
        min-height: 43px !important;
        font-size: .82rem !important;
    }

    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus,
    [data-testid="stDateInput"] input:focus {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 3px rgba(49,87,213,.10) !important;
    }

    [data-baseweb="select"] > div {
        background: #fff !important;
        border-color: #d8dee8 !important;
        border-radius: 9px !important;
        min-height: 43px !important;
    }

    [data-baseweb="select"] * {
        color: var(--ink) !important;
    }

    /* ---------------- BUTTONS ---------------- */

    [data-testid="stButton"] button,
    [data-testid="stDownloadButton"] button {
        min-height: 43px !important;
        border-radius: 9px !important;
        font-weight: 700 !important;
        font-family: var(--font) !important;
        transition: all .15s ease !important;
    }

    [data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(135deg, var(--primary), #2749bc) !important;
        color: #fff !important;
        border: 1px solid var(--primary) !important;
        box-shadow: 0 7px 18px rgba(49,87,213,.20) !important;
    }

    [data-testid="stButton"] button[kind="primary"] *,
    [data-testid="stDownloadButton"] button[kind="primary"] * {
        color: #fff !important;
    }

    [data-testid="stButton"] button[kind="primary"]:hover {
        background: linear-gradient(135deg, var(--primary-dark), #203c9e) !important;
        transform: translateY(-1px);
        box-shadow: 0 10px 24px rgba(49,87,213,.26) !important;
    }

    [data-testid="stButton"] button:not([kind="primary"]),
    [data-testid="stDownloadButton"] button {
        background: #fff !important;
        color: var(--ink) !important;
        border: 1px solid #d5dbe5 !important;
    }

    [data-testid="stButton"] button:not([kind="primary"]) *,
    [data-testid="stDownloadButton"] button * {
        color: var(--ink) !important;
    }

    [data-testid="stButton"] button:not([kind="primary"]):hover,
    [data-testid="stDownloadButton"] button:hover {
        border-color: #9eadd4 !important;
        color: var(--primary) !important;
        background: #fbfcff !important;
    }

    /* ---------------- BADGES ---------------- */

    .badge {
        display: inline-flex;
        align-items: center;
        gap: .35rem;
        border-radius: 999px;
        padding: .38rem .68rem;
        font-family: var(--mono) !important;
        font-size: .61rem;
        font-weight: 600;
        letter-spacing: .03em;
        white-space: nowrap;
    }

    .badge-blue {
        background: var(--primary-soft);
        color: var(--primary);
    }

    .badge-green {
        background: var(--success-soft);
        color: var(--success);
    }

    .badge-amber {
        background: var(--warning-soft);
        color: var(--warning);
    }

    /* ---------------- METRICS ---------------- */

    [data-testid="stMetric"] {
        background: #fff !important;
        border: 1px solid var(--line) !important;
        border-radius: 14px !important;
        padding: 1rem 1.05rem !important;
        box-shadow: var(--shadow-sm);
    }

    [data-testid="stMetricLabel"] {
        color: var(--muted) !important;
        font-size: .68rem !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: .06em;
    }

    [data-testid="stMetricValue"] {
        color: var(--ink) !important;
        font-family: var(--mono) !important;
        font-size: 1.55rem !important;
        font-weight: 600 !important;
    }

    /* ---------------- VERDICT ---------------- */

    .verdict {
        position: relative;
        overflow: hidden;
        border-radius: 18px;
        padding: 1.65rem 1.8rem;
        margin: .25rem 0 1.2rem;
        background:
            radial-gradient(circle at 93% 18%, rgba(105,132,255,.28), transparent 28%),
            linear-gradient(135deg, #111827 0%, #17213a 100%);
        box-shadow: var(--shadow-lg);
    }

    .verdict::after {
        content: "";
        position: absolute;
        width: 180px;
        height: 180px;
        right: -80px;
        bottom: -100px;
        border-radius: 50%;
        border: 1px solid rgba(255,255,255,.07);
    }

    .verdict-kicker {
        color: #91a7ff !important;
        font-family: var(--mono) !important;
        font-size: .61rem;
        font-weight: 600;
        letter-spacing: .14em;
        text-transform: uppercase;
    }

    .verdict-name {
        color: #fff !important;
        font-family: var(--display) !important;
        font-size: 1.72rem;
        font-weight: 800;
        margin-top: .32rem;
        max-width: 78%;
    }

    .verdict-copy {
        color: #aab4c7 !important;
        font-size: .78rem;
        line-height: 1.55;
        max-width: 72%;
        margin-top: .38rem;
    }

    .verdict-rank {
        position: absolute;
        right: 1.6rem;
        top: 1.35rem;
        width: 72px;
        height: 72px;
        border-radius: 50%;
        border: 1px solid rgba(145,167,255,.5);
        background: rgba(255,255,255,.04);
        display: flex;
        align-items: center;
        justify-content: center;
        color: #b7c5ff !important;
        font-family: var(--mono) !important;
        font-size: .67rem;
        font-weight: 600;
        text-align: center;
        line-height: 1.35;
    }

    /* ---------------- RUN / HISTORY ---------------- */

    .run-card {
        background: #fff;
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 1.15rem 1.3rem;
        margin: .65rem 0 .35rem;
        box-shadow: var(--shadow-sm);
    }

    .run-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
    }

    .run-title {
        color: var(--ink);
        font-family: var(--display) !important;
        font-weight: 800;
        font-size: .94rem;
    }

    .run-id {
        color: var(--muted-2);
        font-family: var(--mono) !important;
        font-size: .64rem;
        margin-top: .25rem;
    }

    .run-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(100px, 1fr));
        gap: 1rem;
        margin-top: 1rem;
        padding-top: .9rem;
        border-top: 1px solid #eef0f4;
    }

    .run-label {
        color: var(--muted-2);
        font-family: var(--mono) !important;
        font-size: .57rem;
        text-transform: uppercase;
        letter-spacing: .08em;
    }

    .run-value {
        color: var(--ink);
        font-size: .77rem;
        font-weight: 700;
        margin-top: .18rem;
        word-break: break-word;
    }

    .mono {
        font-family: var(--mono) !important;
    }

    /* ---------------- EXPANDERS / ALERTS ---------------- */

    [data-testid="stExpander"] {
        background: #fff !important;
        border: 1px solid var(--line) !important;
        border-radius: 12px !important;
        margin-bottom: .5rem !important;
        box-shadow: var(--shadow-sm);
    }

    [data-testid="stExpander"] summary {
        color: var(--ink) !important;
        font-weight: 700 !important;
    }

    [data-testid="stAlert"] {
        border-radius: 11px !important;
        font-size: .79rem !important;
    }

    /* ---------------- SCORE CHIPS ---------------- */

    .score-chip {
        display: inline-flex;
        border-radius: 999px;
        padding: .3rem .58rem;
        font-size: .62rem;
        font-weight: 700;
        margin-bottom: .55rem;
    }

    .score-strong { background: var(--success-soft); color: var(--success); }
    .score-moderate { background: var(--warning-soft); color: var(--warning); }
    .score-attention { background: var(--danger-soft); color: var(--danger); }
    .score-neutral { background: #f2f4f7; color: var(--muted); }

    [data-testid="stProgress"] > div {
        background: #edf0f5 !important;
        border-radius: 999px !important;
    }

    [data-testid="stProgress"] > div > div {
        background: linear-gradient(90deg, #3157d5, #6a82eb) !important;
        border-radius: 999px !important;
    }

    /* ---------------- DATAFRAME ---------------- */

    [data-testid="stDataFrame"] {
        border: 1px solid var(--line);
        border-radius: 13px;
        overflow: hidden;
        box-shadow: var(--shadow-sm);
        background: #fff;
    }

    /* ---------------- STATUS ---------------- */

    [data-testid="stStatusWidget"] {
        border-radius: 13px !important;
        border: 1px solid var(--line) !important;
        box-shadow: var(--shadow-sm);
    }

    /* ---------------- MOBILE ---------------- */

    @media (max-width: 900px) {
        .main .block-container {
            padding: 1.4rem 1rem 4rem !important;
        }
        .page-title {
            font-size: 2rem;
        }
        .run-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }
    </style>
    <style>
    /* =====================================================
       PREMIUM MBB / BIG 4 OVERRIDES
       ===================================================== */

    .stApp {
        background:
            radial-gradient(circle at 82% 0%, rgba(49,87,213,.045), transparent 26%),
            #f5f7fa !important;
    }

    .main .block-container {
        max-width: 1440px !important;
        padding: 2.7rem 4rem 5rem !important;
    }

    .page-title {
        font-size: 2.7rem !important;
        letter-spacing: -.045em !important;
    }

    .page-subtitle {
        font-size: .94rem !important;
        max-width: 760px !important;
        color: #667085 !important;
    }

    .header-rule {
        margin: 1.45rem 0 2.15rem !important;
        background: linear-gradient(
            90deg,
            #3157d5 0%,
            #dce3f8 22%,
            transparent 70%
        ) !important;
    }

    /* Strategic section rhythm */
    .section-head {
        margin-top: 2.5rem !important;
        margin-bottom: 1.1rem !important;
    }

    .section-label {
        color: #3157d5 !important;
        font-size: .60rem !important;
    }

    .section-title {
        font-size: 1.38rem !important;
        letter-spacing: -.035em !important;
    }

    /* Executive upload hero */
    .upload-hero {
        position: relative;
        overflow: hidden;
        border: 1px solid #dce2ec;
        border-radius: 20px;
        background: linear-gradient(135deg, #ffffff 0%, #f8faff 100%);
        box-shadow: 0 14px 45px rgba(16,24,40,.06);
        padding: 2rem 2.1rem;
        margin-bottom: .9rem;
    }

    .upload-hero::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        width: 5px;
        height: 100%;
        background: linear-gradient(180deg, #3157d5, #7189e9);
    }

    .upload-hero-grid {
        display: grid;
        grid-template-columns: 1fr 330px;
        gap: 2rem;
        align-items: center;
    }

    .upload-kicker {
        color: #3157d5 !important;
        font-family: var(--mono) !important;
        font-size: .61rem;
        font-weight: 700;
        letter-spacing: .12em;
        text-transform: uppercase;
    }

    .upload-heading {
        color: #172033 !important;
        font-family: var(--display) !important;
        font-size: 1.55rem;
        font-weight: 800;
        letter-spacing: -.035em;
        margin-top: .35rem;
    }

    .upload-copy {
        color: #667085 !important;
        font-size: .82rem;
        line-height: 1.65;
        max-width: 670px;
        margin-top: .4rem;
    }

    .process-panel {
        background: #f2f5fb;
        border: 1px solid #e3e8f2;
        border-radius: 14px;
        padding: 1rem 1.05rem;
    }

    .process-title {
        color: #475467 !important;
        font-family: var(--mono) !important;
        font-size: .59rem;
        font-weight: 700;
        letter-spacing: .1em;
        text-transform: uppercase;
        margin-bottom: .55rem;
    }

    .process-step {
        display: flex;
        align-items: center;
        gap: .55rem;
        color: #475467 !important;
        font-size: .71rem;
        font-weight: 600;
        margin: .42rem 0;
    }

    .process-dot {
        width: 21px;
        height: 21px;
        border-radius: 50%;
        background: #e4eaff;
        color: #3157d5 !important;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-family: var(--mono) !important;
        font-size: .55rem;
        font-weight: 700;
        flex-shrink: 0;
    }

    /* Upload zone */
    [data-testid="stFileUploader"] section {
        min-height: 175px !important;
        border: 1px dashed #aebce1 !important;
        background:
            linear-gradient(180deg, rgba(255,255,255,.98), rgba(248,250,255,.98)) !important;
        box-shadow: inset 0 0 0 4px rgba(49,87,213,.018);
    }

    [data-testid="stFileUploader"] section:hover {
        border-color: #3157d5 !important;
        box-shadow: inset 0 0 0 4px rgba(49,87,213,.035);
    }

    /* Supplier intake cards */
    .doc-card {
        border-left: 3px solid #dbe2f8 !important;
        margin-top: 1rem !important;
        margin-bottom: .8rem !important;
        padding: .95rem 1.1rem !important;
    }

    .doc-number {
        background: #edf1ff !important;
        color: #3157d5 !important;
    }

    /* Evaluation action */
    .evaluation-action {
        border: 1px solid #dfe4ee;
        border-radius: 16px;
        background: #fff;
        padding: 1rem 1.2rem;
        box-shadow: 0 7px 25px rgba(16,24,40,.045);
        margin-top: .4rem;
        margin-bottom: .6rem;
    }

    .evaluation-action-title {
        color: #172033 !important;
        font-weight: 800;
        font-family: var(--display) !important;
        font-size: .94rem;
    }

    .evaluation-action-copy {
        color: #667085 !important;
        font-size: .73rem;
        margin-top: .2rem;
        line-height: 1.45;
    }

    /* KPI cards */
    [data-testid="stMetric"] {
        min-height: 106px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        border: 1px solid #e1e5ec !important;
        border-top: 3px solid #3157d5 !important;
        box-shadow: 0 5px 18px rgba(16,24,40,.045) !important;
    }

    /* Results */
    .verdict {
        min-height: 150px;
        padding: 1.8rem 2rem !important;
        background:
            radial-gradient(circle at 88% 5%, rgba(104,130,235,.30), transparent 28%),
            linear-gradient(135deg, #111827 0%, #18233c 100%) !important;
    }

    .verdict-kicker {
        color: #a9b9ff !important;
    }

    .verdict-name {
        font-size: 1.85rem !important;
    }

    /* History */
    .run-card {
        transition: transform .15s ease, box-shadow .15s ease;
    }

    .run-card:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 28px rgba(16,24,40,.07);
    }

    /* Keep result navigation button visually compact */
    .run-card + div [data-testid="stButton"] button {
        max-width: 220px;
    }

    @media (max-width: 950px) {
        .main .block-container {
            padding: 1.5rem 1rem 4rem !important;
        }
        .upload-hero-grid {
            grid-template-columns: 1fr;
        }
    }
    </style>

    """,
    unsafe_allow_html=True,
)


# =========================================================
# RESULTS RENDERER
# =========================================================

def render_results(state):
    """
    Render evaluation results.

    Works for:
    - freshly completed LangGraph runs
    - historical SQLite runs
    """

    run_id = state.get(
        "rfp_run_id",
        "N/A",
    )

    ranked_results = get_ranked_results(
        state
    )

    if not ranked_results:
        st.warning(
            "No ranked supplier results are available yet. "
            "Run an evaluation to see suppliers filed here."
        )
        return

    ranked_results = sorted(
        ranked_results,
        key=lambda x: (
            x.get("final_rank")
            if x.get("final_rank") is not None
            else 999
        ),
    )

    # =====================================================
    # HEADER
    # =====================================================

    st.markdown(
        html(
            """
            <div class="section-label">
                Case File · Verdict
            </div>

            <div class="section-title">
                Evaluation Results
            </div>

            <div class="section-copy">
                Final supplier ranking based on weighted
                evaluation, peer benchmarking and
                deterministic ranking.
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        html(
            f"""
            <div class="info-strip">
                RFP Run ID ·
                <span class="mono-value">{run_id}</span>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    # =====================================================
    # WINNER  (verdict stamp -- signature element)
    # =====================================================

    winner = ranked_results[0]

    winner_name = winner.get(
        "supplier_name",
        "N/A",
    )

    st.markdown(
        html(
            f"""
            <div class="verdict">
                <div class="verdict-rank">TOP<br>RANK<br>#1</div>
                <div class="verdict-kicker">Recommended supplier</div>
                <div class="verdict-name">{winner_name}</div>
                <div class="verdict-copy">
                    Highest-ranked proposal based on the evaluated criteria,
                    peer benchmarking and deterministic ranking.
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    # =====================================================
    # METRICS
    # =====================================================

    total_suppliers = len(
        ranked_results
    )

    scores = [
        float(
            s.get(
                "absolute_score",
                0,
            ) or 0
        )
        for s in ranked_results
    ]

    ppis = [
        float(
            s.get(
                "ppi",
                0,
            ) or 0
        )
        for s in ranked_results
    ]

    average_score = (
        sum(scores) / len(scores)
        if scores
        else 0
    )

    average_ppi = (
        sum(ppis) / len(ppis)
        if ppis
        else 0
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Suppliers",
            total_suppliers,
        )

    with c2:
        st.metric(
            "Top Score",
            f"{scores[0]:.1f}",
        )

    with c3:
        st.metric(
            "Average Score",
            f"{average_score:.1f}",
        )

    with c4:
        st.metric(
            "Average PPI",
            f"{average_ppi:.1f}",
        )

    # =====================================================
    # LEADERBOARD
    # =====================================================

    st.markdown(
        html(
            """
            <div class="section-head">
                <div class="section-label">
                    Ledger
                </div>
                <div class="section-title">
                    Supplier Leaderboard
                </div>
                <div class="section-copy">
                    Compare all evaluated suppliers.
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    leaderboard = []

    for supplier in ranked_results:

        rank_value = supplier.get(
            "final_rank"
        )

        leaderboard.append(
            {
                "Rank":
                    rank_marker(
                        rank_value
                    ),

                "Supplier":
                    supplier.get(
                        "supplier_name"
                    ),

                "Absolute Score":
                    round(
                        float(
                            supplier.get(
                                "absolute_score",
                                0,
                            ) or 0
                        ),
                        2,
                    ),

                "PPI":
                    round(
                        float(
                            supplier.get(
                                "ppi",
                                0,
                            ) or 0
                        ),
                        2,
                    ),

                "Experience":
                    round(
                        float(
                            supplier.get(
                                "experience_rating",
                                0,
                            ) or 0
                        ),
                        1,
                    ),
            }
        )

    try:

        st.dataframe(
            leaderboard,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rank": st.column_config.TextColumn(
                    "Rank",
                    width="small",
                ),
                "Absolute Score": st.column_config.ProgressColumn(
                    "Absolute Score",
                    min_value=0,
                    max_value=100,
                    format="%.1f",
                ),
                "PPI": st.column_config.ProgressColumn(
                    "PPI",
                    min_value=0,
                    max_value=100,
                    format="%.1f",
                ),
            },
        )

    except Exception:

        # Fall back to a plain table if the installed
        # Streamlit version does not support column_config
        # progress columns -- keeps the app functional.

        st.dataframe(
            leaderboard,
            use_container_width=True,
            hide_index=True,
        )

    # =====================================================
    # SCORECARD
    # =====================================================

    st.markdown(
        html(
            """
            <div class="section-head">
                <div class="section-label">
                    Detail
                </div>
                <div class="section-title">
                    Supplier Scorecard
                </div>
                <div class="section-copy">
                    Review detailed performance for an
                    individual supplier.
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    supplier_names = [
        s.get("supplier_name")
        for s in ranked_results
    ]

    selected_name = st.selectbox(
        "Select supplier",
        supplier_names,
        key=f"supplier_detail_{run_id}",
    )

    selected_supplier = next(
        s
        for s in ranked_results
        if s.get("supplier_name")
        == selected_name
    )

    # =====================================================
    # SUPPLIER METRICS
    # =====================================================

    c1, c2, c3, c4 = st.columns(4)

    with c1:

        rank = selected_supplier.get(
            "final_rank"
        )

        st.metric(
            "Final Rank",
            f"#{rank}" if rank else "—",
        )

    with c2:

        st.metric(
            "Absolute Score",
            (
                f"{float(selected_supplier.get('absolute_score', 0) or 0):.1f}"
            ),
        )

    with c3:

        st.metric(
            "PPI",
            (
                f"{float(selected_supplier.get('ppi', 0) or 0):.1f}"
            ),
        )

    with c4:

        st.metric(
            "Experience",
            (
                f"{float(selected_supplier.get('experience_rating', 0) or 0):.1f}/10"
            ),
        )

    # =====================================================
    # RESULT JSON
    # =====================================================

    result_json = parse_json(
        selected_supplier.get(
            "result_json",
            {},
        )
    )

    # =====================================================
    # CRITERION RESULTS
    # =====================================================

    criterion_results = result_json.get(
        "criterion_results",
        [],
    )

    if not criterion_results:

        criterion_results = result_json.get(
            "criteria",
            [],
        )

    st.markdown(
        html(
            """
            <div class="section-head">
                <div class="section-label">
                    Evidence
                </div>
                <div class="section-title">
                    Criterion Performance
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    if not criterion_results:

        st.info(
            "Detailed criterion-level information is "
            "not available for this result."
        )

    else:

        for criterion in criterion_results:

            criterion_name = (
                criterion.get(
                    "criterion_name"
                )
                or criterion.get(
                    "name"
                )
                or (
                    "Criterion "
                    + str(
                        criterion.get(
                            "criterion_id",
                            "",
                        )
                    )
                )
            )

            score = float(
                criterion.get(
                    "score",
                    0,
                ) or 0
            )

            max_score = float(
                criterion.get(
                    "max_score",
                    10,
                ) or 10
            )

            band_class, band_label = score_band(
                score,
                max_score,
            )

            with st.expander(
                f"{criterion_name}  ·  "
                f"{score:.1f}/{max_score:.1f}"
            ):

                st.markdown(
                    html(
                        f"""
                        <span class="score-chip score-{band_class}">
                            {band_label}
                        </span>
                        """
                    ),
                    unsafe_allow_html=True,
                )

                if max_score > 0:

                    st.progress(
                        min(
                            score / max_score,
                            1.0,
                        )
                    )

                justification = criterion.get(
                    "justification"
                )

                evidence = criterion.get(
                    "evidence"
                )

                if justification:

                    st.markdown(
                        "**Assessment**"
                    )

                    st.write(
                        justification
                    )

                if evidence:

                    st.markdown(
                        "**Supporting Evidence**"
                    )

                    st.info(
                        evidence
                    )

    # =====================================================
    # EXPORT
    # =====================================================

    st.markdown(
        html(
            """
            <div class="section-head">
                <div class="section-label">
                    Archive
                </div>
                <div class="section-title">
                    Export
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    export_data = json.dumps(
        state,
        indent=2,
        ensure_ascii=False,
        default=str,
    )

    st.download_button(
        "↓  Download Evaluation JSON",
        data=export_data,
        file_name=(
            f"rfp_evaluation_{run_id}.json"
        ),
        mime="application/json",
        key=f"download_{run_id}",
    )


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown(
        html(
            """
            <div class="brand">
                <span class="brand-mark">◆</span>
                <span class="brand-name">RFP Evaluator</span>
                <div class="brand-sub">Procurement intelligence</div>
            </div>

            <div class="sidebar-caption">Workspace</div>
            """
        ),
        unsafe_allow_html=True,
    )

    selected_page = st.radio(
        "Workspace",
        ["New Evaluation", "Previous Evaluations"],
        index=(
            0
            if st.session_state.page == "New Evaluation"
            else 1
        ),
        label_visibility="collapsed",
        key="navigation_radio",
    )

    st.session_state.page = selected_page

    st.markdown(
        html(
            """
            <div class="sidebar-section">
                <div class="sidebar-caption">Evaluation engine</div>
                <div class="sidebar-feature">✓ AI-assisted evaluation</div>
                <div class="sidebar-feature">✓ Deterministic scoring</div>
                <div class="sidebar-feature">✓ Peer benchmarking</div>
                <div class="sidebar-feature">✓ Auditable ranking</div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


# =========================================================
# NEW EVALUATION
# =========================================================

if st.session_state.page == "New Evaluation":

    st.markdown(
        html(
            """
            <div class="eyebrow">Procurement intelligence · RFP evaluation</div>
            <div class="page-title">RFP Proposal Evaluator</div>
            <div class="page-subtitle">
                Evaluate supplier proposals with AI, compare them consistently,
                and produce a transparent, auditable ranking.
            </div>
            <div class="header-rule"></div>
            """
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        html(
            """
            <div class="upload-hero">
                <div class="upload-hero-grid">
                    <div>
                        <div class="upload-kicker">Proposal intake · Step 01</div>
                        <div class="upload-heading">Bring your proposals together</div>
                        <div class="upload-copy">
                            Upload supplier responses once and let the evaluation engine
                            structure, assess and benchmark them consistently. Multiple
                            PDF submissions can be processed in a single evaluation run.
                        </div>
                    </div>

                    <div class="process-panel">
                        <div class="process-title">Evaluation flow</div>
                        <div class="process-step">
                            <span class="process-dot">01</span>
                            Extract proposal content
                        </div>
                        <div class="process-step">
                            <span class="process-dot">02</span>
                            Assess evaluation criteria
                        </div>
                        <div class="process-step">
                            <span class="process-dot">03</span>
                            Benchmark &amp; rank
                        </div>
                    </div>
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "Upload supplier RFP PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if not uploaded_files:
        st.markdown(
            html(
                """
                <div style="
                    text-align:center;
                    color:#98a2b3;
                    font-size:.76rem;
                    margin-top:.55rem;
                ">
                    PDF only · Multiple proposals supported
                </div>
                """
            ),
            unsafe_allow_html=True,
        )
        st.info("Upload one or more supplier PDF proposals to begin.")

    else:

        st.markdown(
            html(
                f"""
                <span class="badge badge-blue">
                    {len(uploaded_files)} proposal(s) ready
                </span>
                """
            ),
            unsafe_allow_html=True,
        )

        st.markdown(
            html(
                """
                <div class="section-head">
                    <div class="section-label">01 · Intake</div>
                    <div class="section-title">Supplier information</div>
                    <div class="section-copy">
                        Add the metadata used alongside each proposal during evaluation.
                    </div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        suppliers = []
        validation_errors = []

        for index, uploaded_file in enumerate(uploaded_files):

            base_name = os.path.splitext(uploaded_file.name)[0]

            default_name = (
                base_name
                .replace("_", " ")
                .replace("-", " ")
                .title()
            )

            safe_key = (
                f"{index}_"
                f"{uploaded_file.name}_"
                f"{uploaded_file.size}"
            )

            st.markdown(
                html(
                    f"""
                    <div class="doc-card">
                        <div class="doc-number">{index + 1:02d}</div>
                        <div>
                            <div class="doc-name">{uploaded_file.name}</div>
                            <div class="doc-meta">PDF supplier proposal</div>
                        </div>
                    </div>
                    """
                ),
                unsafe_allow_html=True,
            )

            col1, col2, col3 = st.columns(
                [2.4, 1.5, 1.2],
                gap="medium",
            )

            with col1:
                supplier_name = st.text_input(
                    "Supplier Name",
                    value=default_name,
                    key=f"name_{safe_key}",
                )

            with col2:
                submission_date = st.date_input(
                    "Submission Date",
                    value=date.today(),
                    key=f"date_{safe_key}",
                )

            with col3:
                experience = st.number_input(
                    "Historical Experience",
                    min_value=0.0,
                    max_value=10.0,
                    value=5.0,
                    step=0.5,
                    key=f"experience_{safe_key}",
                )

            if not supplier_name.strip():
                validation_errors.append(
                    f"Supplier name is missing for {uploaded_file.name}."
                )

            safe_filename = (
                uploaded_file.name
                .replace(" ", "_")
                .replace("/", "_")
                .replace("\\", "_")
            )

            pdf_path = UPLOAD_DIR / safe_filename

            with open(pdf_path, "wb") as file:
                file.write(uploaded_file.getbuffer())

            suppliers.append(
                {
                    "supplier_id": f"SUP{index + 1:03d}",
                    "supplier_name": supplier_name.strip(),
                    "submission_date": submission_date.isoformat(),
                    "experience_rating": float(experience),
                    "pdf_path": str(pdf_path),
                }
            )

        for error in validation_errors:
            st.error(error)

        st.markdown(
            html(
                """
                <div class="section-head">
                    <div class="section-label">02 · Evaluation</div>
                    <div class="section-title">Run evaluation</div>
                    <div class="section-copy">
                        Extract proposal content, score active criteria,
                        benchmark suppliers and calculate the final ranking.
                    </div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        st.markdown(
            html(
                """
                <div class="evaluation-action">
                    <div class="evaluation-action-title">Ready to evaluate</div>
                    <div class="evaluation-action-copy">
                        The run will evaluate every uploaded proposal using the configured
                        criteria and return a ranked, auditable supplier comparison.
                    </div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        evaluate = st.button(
            "▶  Start Evaluation",
            type="primary",
            use_container_width=True,
            disabled=bool(validation_errors),
        )

        if evaluate:

            initial_state = {
                "suppliers": suppliers,
                "current_supplier_index": 0,
                "criteria": [],
                "supplier_scores": [],
                "benchmark_results": {},
                "ranked_results": [],
                "warnings": [],
                "errors": [],
                "status": "STARTING",
            }

            try:
                graph = build_rfp_graph()
            except Exception as exc:
                st.error(f"Unable to build evaluation workflow: {exc}")
                st.stop()

            with st.status(
                "Running evaluation...",
                expanded=True,
            ) as status:

                st.write(
                    f"Evaluating {len(suppliers)} supplier proposal(s)..."
                )

                try:
                    final_state = graph.invoke(initial_state)

                except Exception as exc:
                    status.update(
                        label="Evaluation failed",
                        state="error",
                    )
                    st.error(f"Evaluation failed: {exc}")
                    st.stop()

                status.update(
                    label="Evaluation completed",
                    state="complete",
                )

            st.session_state.current_result = final_state
            st.rerun()

    if st.session_state.current_result:

        st.markdown(
            html(
                """
                <div class="section-head">
                    <div class="section-label">03 · Results</div>
                    <div class="section-title">Latest evaluation</div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

        render_results(st.session_state.current_result)


# =========================================================
# PREVIOUS EVALUATIONS
# =========================================================

elif st.session_state.page == "Previous Evaluations":

    selected_run_id = st.session_state.selected_run_id

    # -----------------------------------------------------
    # SELECTED RUN — dedicated results view
    # -----------------------------------------------------

    if selected_run_id:

        st.markdown(
            html(
                """
                <div class="eyebrow">Archive · Selected evaluation</div>
                <div class="page-title">Evaluation results</div>
                <div class="page-subtitle">
                    Detailed supplier ranking and evidence from the selected
                    completed evaluation run.
                </div>
                <div class="header-rule"></div>
                """
            ),
            unsafe_allow_html=True,
        )

        topbar_left, topbar_right = st.columns([1, 5])

        with topbar_left:
            if st.button(
                "←  Evaluation history",
                key="back_to_runs",
                use_container_width=True,
            ):
                st.session_state.selected_run_id = None
                st.rerun()

        selected_results = get_run_results(selected_run_id)

        if not selected_results:
            st.warning(
                "This evaluation has no persisted supplier results."
            )
        else:

            previous_state = {
                "rfp_run_id": selected_run_id,
                "status": "COMPLETE",
                "ranked_results": selected_results,
                "errors": [],
                "warnings": [],
            }

            render_results(previous_state)

    # -----------------------------------------------------
    # RUN LIST
    # -----------------------------------------------------

    else:

        st.markdown(
            html(
                """
                <div class="eyebrow">Archive · Evaluation history</div>
                <div class="page-title">Previous evaluations</div>
                <div class="page-subtitle">
                    Review completed evaluation runs and reopen any result
                    set without rerunning the analysis.
                </div>
                <div class="header-rule"></div>
                """
            ),
            unsafe_allow_html=True,
        )

        previous_runs = get_previous_runs()

        st.markdown(
            html(
                f"""
                <span class="badge badge-green">
                    ● {len(previous_runs)} completed evaluation(s)
                </span>
                """
            ),
            unsafe_allow_html=True,
        )

        st.write("")

        if not previous_runs:

            st.info(
                "No completed evaluations are on file yet. "
                "Run a new evaluation to start building the archive."
            )

        else:

            for run in previous_runs:

                run_id = run["rfp_run_id"]
                created_at = run["created_at"]
                supplier_count = run["supplier_count"]

                try:
                    results = get_run_results(run_id)
                except Exception:
                    results = []

                results = sorted(
                    results,
                    key=lambda x: (
                        x.get("final_rank")
                        if x.get("final_rank") is not None
                        else 999
                    ),
                )

                top_supplier = results[0] if results else None

                top_name = (
                    top_supplier.get("supplier_name")
                    if top_supplier
                    else "—"
                )

                top_score = (
                    top_supplier.get("absolute_score")
                    if top_supplier
                    else None
                )

                st.markdown(
                    html(
                        f"""
                        <div class="run-card">
                            <div class="run-top">
                                <div>
                                    <div class="run-title">Evaluation Run</div>
                                    <div class="run-id">{run_id}</div>
                                </div>
                                <span class="badge badge-green">● Completed</span>
                            </div>

                            <div class="run-grid">
                                <div>
                                    <div class="run-label">Created</div>
                                    <div class="run-value mono">{created_at}</div>
                                </div>
                                <div>
                                    <div class="run-label">Suppliers</div>
                                    <div class="run-value mono">{supplier_count}</div>
                                </div>
                                <div>
                                    <div class="run-label">Top supplier</div>
                                    <div class="run-value">{top_name}</div>
                                </div>
                                <div>
                                    <div class="run-label">Top score</div>
                                    <div class="run-value mono">
                                        {
                                            f"{float(top_score):.1f}"
                                            if top_score is not None
                                            else "—"
                                        }
                                    </div>
                                </div>
                            </div>
                        </div>
                        """
                    ),
                    unsafe_allow_html=True,
                )

                if st.button(
                    "View Results →",
                    key=f"view_{run_id}",
                    use_container_width=True,
                ):
                    st.session_state.selected_run_id = run_id
                    st.rerun()









