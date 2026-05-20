import streamlit as st
import pandas as pd
import random
import time
import base64
from datetime import datetime, date, timedelta
from pathlib import Path
from PIL import Image

from database import (
    verify_login, change_password, hash_password, get_connection,
    get_all_emitters, get_emitter_by_name, get_emitter_by_id,
    get_all_readings, get_readings_by_date_range,
    get_emissions_statistics, get_compliance_statistics,
    save_reading, get_all_alerts, save_alert, resolve_alert,
    get_all_users, add_user, toggle_user_active, delete_user,
    register_emitter_with_portal,
    add_compliance_action, get_all_compliance_actions,
    get_all_settings, set_setting, setup_database,
    is_strong_password,
    get_notification_settings, save_notification_settings,
    send_email_message, send_sms_via_gateway,
    build_report,
)

# ── Ensure DB exists ──────────────────────────────────────────
try:
    get_all_emitters()
except Exception:
    setup_database()

CO2_LIMIT = 450.0
CH4_LIMIT = 25.0
BASE_DIR = Path(__file__).resolve().parent
APP_ICON_PATH = BASE_DIR / "271758865_293023766200463_4775874385363987956_n.jpg"
APP_BACKGROUND_PATH = BASE_DIR / "background.jpg"
APP_ICON = Image.open(APP_ICON_PATH) if APP_ICON_PATH.exists() else "🌿"
APP_BACKGROUND = (
    base64.b64encode(APP_BACKGROUND_PATH.read_bytes()).decode("utf-8")
    if APP_BACKGROUND_PATH.exists()
    else ""
)

st.set_page_config(
    page_title="GHG Monitor — Makoni District",
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════
# GLOBAL CSS
# ══════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html,body,[class*="css"],.stApp{font-family:'Inter',sans-serif !important}

/* ── Sidebar ── */
section[data-testid="stSidebar"]{background:#060f0a !important;border-right:1px solid #1a3a25 !important}
section[data-testid="stSidebar"]>div{padding-top:0 !important}
section[data-testid="stSidebar"] *{color:#c8e6d4 !important}
section[data-testid="stSidebar"] .stButton>button{
    background:rgba(46,184,114,0.1) !important;border:1px solid rgba(46,184,114,0.25) !important;
    color:#7dd9a8 !important;border-radius:10px !important;width:100% !important;
    font-size:13px !important;font-weight:500 !important;transition:all .15s ease !important}
section[data-testid="stSidebar"] .stButton>button:hover{
    background:rgba(46,184,114,0.22) !important;border-color:rgba(46,184,114,0.5) !important}

/* ── App background ── */
.stApp{background:#f7faf8 !important}
.block-container{padding-top:1.5rem !important;max-width:100% !important}

/* ── Metric cards ── */
div[data-testid="metric-container"]{
    background:white !important;border:1px solid #e2ede8 !important;border-radius:16px !important;
    padding:20px 22px !important;box-shadow:0 1px 8px rgba(13,51,33,.05) !important;
    transition:all .2s ease !important;position:relative;overflow:hidden}
div[data-testid="metric-container"]::before{
    content:'';position:absolute;top:0;left:0;right:0;height:3px;
    background:linear-gradient(90deg,#2eb872,#0d9e5e);border-radius:16px 16px 0 0}
div[data-testid="metric-container"]:hover{transform:translateY(-3px) !important;box-shadow:0 8px 24px rgba(13,51,33,.12) !important}
div[data-testid="metric-container"] label{font-size:11px !important;font-weight:600 !important;letter-spacing:.1em !important;text-transform:uppercase !important;color:#7a9e88 !important}
div[data-testid="metric-container"] [data-testid="stMetricValue"]{font-size:30px !important;font-weight:700 !important;color:#0a2a18 !important;font-family:'JetBrains Mono',monospace !important}

/* ── Tabs ── */
button[data-baseweb="tab"]{font-family:'Inter',sans-serif !important;font-weight:500 !important;font-size:13px !important;color:#7a9e88 !important;padding:14px 18px !important}
button[data-baseweb="tab"][aria-selected="true"]{color:#0a2a18 !important;font-weight:600 !important}

/* ── Cards ── */
.ghg-card{background:white;border:1px solid #e2ede8;border-radius:16px;padding:20px 24px;box-shadow:0 1px 6px rgba(13,51,33,.04);margin-bottom:16px}
.ghg-card-title{font-size:14px;font-weight:600;color:#0a2a18;letter-spacing:-.01em;margin-bottom:14px}

/* ── Badges ── */
.badge{display:inline-flex;align-items:center;font-size:11px;font-weight:700;padding:4px 11px;border-radius:20px;letter-spacing:.03em}
.badge-compliant{background:#d4f0e0;color:#0d5c2e}
.badge-warning{background:#fff3cd;color:#7a4f00}
.badge-critical{background:#ffe0e0;color:#7a0000}
.badge-road{background:#e3eeff;color:#1a3fa3}

/* ── Alert boxes ── */
.alert-critical{background:#fff5f5;border:1px solid #ffcdd2;border-left:4px solid #e53935;padding:14px 18px;border-radius:12px;margin:8px 0}
.alert-warning{background:#fffbf0;border:1px solid #ffe082;border-left:4px solid #f5a623;padding:14px 18px;border-radius:12px;margin:8px 0}
.alert-ok{background:#f0fff5;border:1px solid #a5d6b0;border-left:4px solid #2eb872;padding:14px 18px;border-radius:12px;margin:8px 0}

/* ── Table ── */
.ghg-table{width:100%;border-collapse:collapse;font-size:13.5px}
.ghg-table thead tr{background:#f7faf8;border-bottom:2px solid #e2ede8}
.ghg-table th{padding:11px 14px;text-align:left;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:#7a9e88;font-weight:600}
.ghg-table tbody tr{border-bottom:1px solid #f0f5f2;transition:background .12s}
.ghg-table tbody tr:hover{background:#f7faf8}
.ghg-table td{padding:13px 14px;color:#0a2a18;vertical-align:middle}
.td-name{font-weight:600;color:#0a2a18}
.td-type{color:#7a9e88;font-size:12px}
.td-num{font-family:'JetBrains Mono',monospace;font-size:13px}

/* ── Progress bars ── */
.pbar{background:#f0f5f2;border-radius:8px;height:7px;overflow:hidden;min-width:80px;display:inline-block;width:72px}
.pfill{height:100%;border-radius:8px;transition:width .5s ease}

/* ── Section headers ── */
.section-hdr{font-size:10.5px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#7a9e88;margin:0 0 14px 0}

/* ── KPI boxes ── */
.kpi-box{background:white;border:1px solid #e2ede8;border-radius:14px;padding:16px 18px;position:relative;overflow:hidden;box-shadow:0 1px 6px rgba(13,51,33,.04);transition:all .2s;height:100%}
.kpi-box:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(13,51,33,.1)}
.kpi-accent{position:absolute;top:0;left:0;right:0;height:3px;border-radius:14px 14px 0 0}
.kpi-label{font-size:10.5px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:#7a9e88;margin-bottom:6px}
.kpi-value{font-size:26px;font-weight:700;font-family:'JetBrains Mono',monospace;color:#0a2a18;line-height:1}
.kpi-unit{font-size:11px;color:#7a9e88;margin-top:4px}
.kpi-delta{font-size:11px;margin-top:6px;display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:20px}
.kpi-delta-red{background:#ffe0e0;color:#c0392b}
.kpi-delta-green{background:#d4f0e0;color:#1a7a40}

/* ── Page title ── */
.page-title{font-size:24px;font-weight:700;color:#0a2a18;margin:0;letter-spacing:-.02em}
.page-sub{font-size:12px;color:#7a9e88;margin-top:4px}

/* ── Misc ── */
.fancy-divider{border:none;height:1px;background:linear-gradient(90deg,transparent,#d0e8da 20%,#d0e8da 80%,transparent);margin:20px 0}
.auto-badge{display:inline-flex;align-items:center;gap:5px;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:3px 9px;border-radius:20px;background:#fff3cd;color:#856404}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:5px}
.dot-green{background:#2eb872}
.dot-amber{background:#f5a623}
.dot-red{background:#e53935;animation:blink 1.2s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.portal-card{background:#0a2a18;border-radius:20px;padding:28px;color:white;margin-bottom:20px}
.portal-stat{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.15);border-radius:12px;padding:14px 16px;text-align:center}
div[data-testid="stDataFrame"]{border-radius:14px !important;overflow:hidden !important;border:1px solid #e2ede8 !important}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# ALGORITHMS
# ══════════════════════════════════════════════════════════════

if APP_BACKGROUND:
    st.markdown(f"""
    <style>
    .stApp {{
        background:
            linear-gradient(rgba(247,250,248,.90), rgba(247,250,248,.94)),
            url("data:image/jpeg;base64,{APP_BACKGROUND}") center center / cover fixed !important;
    }}
    [data-testid="stHeader"] {{
        background:rgba(247,250,248,.78) !important;
        backdrop-filter:blur(8px);
    }}
    section[data-testid="stSidebar"] {{
        background:rgba(6,15,10,.96) !important;
        backdrop-filter:blur(8px);
    }}
    </style>
    """, unsafe_allow_html=True)


def classify(co2: float, ch4: float) -> str:
    if co2 < 0.8 * CO2_LIMIT and ch4 < 0.8 * CH4_LIMIT:
        return "Compliant"
    if co2 > CO2_LIMIT or ch4 > CH4_LIMIT:
        return "Critical"
    return "Warning"


def get_strategies(co2: float, ch4: float) -> list[str]:
    s = []
    if co2 > CO2_LIMIT:
        s += ["Improve energy efficiency", "Switch to renewable energy", "Optimise combustion"]
    if ch4 > CH4_LIMIT:
        s += ["Implement anaerobic digestion", "Reduce agricultural waste", "Monitor wetland release"]
    return s or ["Maintain current emission controls"]


def suggest_penalty(breach_count: int, exceedance_pct: float) -> dict:
    """GAP FIX: Automated rule-based penalty suggestion engine."""
    if breach_count >= 5 or exceedance_pct > 30:
        return {"level": "Suspension", "amount": 5000,
                "reason": f"{breach_count} breaches / {exceedance_pct:.0f}% over limit"}
    if breach_count >= 3 or exceedance_pct > 15:
        return {"level": "Fine", "amount": 2000,
                "reason": f"{breach_count} breaches / {exceedance_pct:.0f}% over limit"}
    if breach_count >= 1:
        return {"level": "Notice", "amount": 0, "reason": "First offence warning"}
    return {"level": "None", "amount": 0, "reason": "Compliant"}


def get_breach_count(emitter_id: int) -> int:
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM alerts WHERE emitter_id=? AND resolved=0", (emitter_id,))
    count  = cursor.fetchone()[0]
    conn.close()
    return count


def load_live_readings() -> list[dict]:
    """GAP FIX: Use real DB readings when available; simulate only when no recent data."""
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.emitter_id, e.name, e.type, r.co2, r.ch4, r.timestamp
        FROM readings r JOIN emitters e ON r.emitter_id = e.id
        WHERE r.timestamp >= datetime('now','-10 minutes')
        ORDER BY r.timestamp DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    if rows:
        seen, result = set(), []
        for row in rows:
            if row[0] not in seen:
                seen.add(row[0])
                result.append({"id": row[0], "name": row[1], "type": row[2],
                                "co2": row[3], "ch4": row[4], "source": "live"})
        return result

    emitters = get_all_emitters()
    return [{"id": e["id"], "name": e["name"], "type": e["type"],
             "co2": round(random.uniform(310, 540), 1),
             "ch4": round(random.uniform(9, 33), 1), "source": "simulated"}
            for e in emitters]


def load_latest_readings(limit: int = 20) -> pd.DataFrame:
    conn = get_connection()
    try:
        return pd.read_sql_query("""
            SELECT *
            FROM readings
            ORDER BY timestamp DESC
            LIMIT ?
        """, conn, params=(limit,))
    finally:
        conn.close()


def status_badge_html(s: str) -> str:
    dot_cls   = {"Compliant": "dot-green", "Warning": "dot-amber", "Critical": "dot-red"}.get(s, "")
    badge_cls = {"Compliant": "badge-compliant", "Warning": "badge-warning", "Critical": "badge-critical"}.get(s, "")
    return f'<span class="badge {badge_cls}"><span class="dot {dot_cls}"></span>{s}</span>'


def bar_html(value: float, limit: float) -> str:
    pct = min(100, value / limit * 100)
    col = "#2eb872" if pct < 80 else ("#f5a623" if pct <= 100 else "#e53935")
    return (f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div class="pbar"><div class="pfill" style="width:{pct:.0f}%;background:{col}"></div></div>'
            f'<span style="font-size:10px;color:#7a9e88;font-family:\'JetBrains Mono\',monospace">{pct:.0f}%</span>'
            f'</div>')


# ══════════════════════════════════════════════════════════════
# AUTO-ALERT  (GAP FIX: fires automatically on breach)
# ══════════════════════════════════════════════════════════════

def auto_notify_breach(emitter: dict, co2: float, ch4: float, status: str):
    notif = get_notification_settings()
    if not all([notif["smtp_host"], notif["smtp_user"], notif["smtp_pass"], notif["smtp_from"]]):
        return
    contact_email = emitter.get("contact_email", "")
    if not contact_email:
        return
    try:
        send_email_message(
            notif["smtp_host"], int(notif["smtp_port"]),
            notif["smtp_user"], notif["smtp_pass"], notif["smtp_from"],
            contact_email,
            f"EMA ALERT: {status} — {emitter['name']}",
            (f"Automated alert from EMA Makoni District GHG Monitoring System.\n\n"
             f"Facility : {emitter['name']}\nStatus   : {status}\n"
             f"CO₂      : {co2} ppm  (Limit: {CO2_LIMIT} ppm)\n"
             f"CH₄      : {ch4} ppm  (Limit: {CH4_LIMIT} ppm)\n"
             f"Time     : {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
             f"Immediate corrective action is required.\n"
             f"Environmental Management Agency | Makoni District")
        )
    except Exception:
        pass
    if emitter.get("contact_phone") and notif.get("sms_gateway"):
        try:
            send_sms_via_gateway(
                notif["smtp_host"], int(notif["smtp_port"]),
                notif["smtp_user"], notif["smtp_pass"], notif["smtp_from"],
                emitter["contact_phone"], notif["sms_gateway"],
                f"EMA ALERT: {emitter['name']} — {status}. CO2={co2}, CH4={ch4}. Act immediately."
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════

def show_login():
    _, col, _ = st.columns([1, 1.3, 1])
    with col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if APP_ICON_PATH.exists():
            _, logo_col, _ = st.columns([1, 1, 1])
            with logo_col:
                st.image(str(APP_ICON_PATH), width=140)
        st.markdown("""
        <div style="text-align:center;margin-bottom:32px">
            <div style="font-size:24px;font-weight:700;color:#0a2a18;letter-spacing:-.02em">GHG Monitoring System</div>
            <div style="font-size:13px;color:#7a9e88;margin-top:6px">Environmental Management Agency · Makoni District</div>
        </div>
        """, unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            st.markdown("<br>", unsafe_allow_html=True)
            submit = st.form_submit_button("Sign In →", width="stretch", type="primary")
        if submit:
            if not username or not password:
                st.error("Please enter both username and password.")
            else:
                result = verify_login(username, password)
                if "user" in result:
                    st.session_state.update({
                        "user": result["user"], "logged_in": True,
                        "session_start": datetime.now().strftime("%H:%M · %d %b %Y")
                    })
                    st.rerun()
                elif result.get("error") == "locked":
                    st.error(f"Account locked until {result.get('until', 'a few minutes')}.")
                elif result.get("error") == "disabled":
                    st.error("Account disabled. Contact the District Officer.")
                else:
                    st.error("Invalid username or password.")
        st.markdown('<div style="text-align:center;margin-top:14px;font-size:12px;color:#7a9e88">Forgot credentials? Contact the District Administrator.</div>',
                    unsafe_allow_html=True)


if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    show_login()
    st.stop()

user = st.session_state.get("user")
if not user or not isinstance(user, dict):
    st.error("Session user not initialized. Please login again.")
    st.stop()
is_admin   = user["role"] == "admin"
is_emitter = user["role"] == "emitter"


# ══════════════════════════════════════════════════════════════
# EMITTER PORTAL  (GAP FIX: per-facility isolated view)
# ══════════════════════════════════════════════════════════════

if is_emitter and user.get("emitter_id"):
    eid  = user["emitter_id"]
    emtr = get_emitter_by_id(eid)
    conn = get_connection()
    c    = conn.cursor()
    c.execute("SELECT co2, ch4, timestamp FROM readings WHERE emitter_id=? ORDER BY timestamp DESC LIMIT 50", (eid,))
    my_readings = c.fetchall()
    c.execute("SELECT alert_type, message, timestamp, resolved FROM alerts WHERE emitter_id=? ORDER BY timestamp DESC LIMIT 20", (eid,))
    my_alerts = c.fetchall()
    conn.close()

    with st.sidebar:
        st.markdown("""
        <div style="padding:22px 18px 18px;border-bottom:1px solid #1a3a25;margin-bottom:16px">
            <div style="font-size:20px;font-weight:700">🌿 GHG Monitor</div>
            <div style="font-size:10px;opacity:.5;margin-top:2px;letter-spacing:.06em;text-transform:uppercase">Emitter Portal · EMA</div>
        </div>""", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="background:rgba(46,184,114,0.08);border:1px solid rgba(46,184,114,0.18);border-radius:12px;padding:12px 14px;margin-bottom:18px">
            <div style="font-size:11px;opacity:.5;letter-spacing:.07em;text-transform:uppercase;margin-bottom:4px">Logged in as</div>
            <div style="font-size:14px;font-weight:600">{user['full_name']}</div>
        </div>""", unsafe_allow_html=True)
        if st.button("🚪  Logout"):
            for k in ["user", "logged_in", "session_start"]:
                st.session_state.pop(k, None)
            st.rerun()

    latest_co2 = my_readings[0][0] if my_readings else 0.0
    latest_ch4 = my_readings[0][1] if my_readings else 0.0
    status     = classify(latest_co2, latest_ch4)
    badge_html = status_badge_html(status)

    st.markdown(f"""
    <div class="portal-card">
        <div style="font-size:11px;opacity:.5;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px">Emitter Portal</div>
        <div style="font-size:22px;font-weight:700">{emtr['name'] if emtr else 'My Facility'}</div>
        <div style="font-size:13px;opacity:.6;margin-top:4px">📍 {emtr.get('location','') if emtr else ''}</div>
        <div style="margin-top:8px">{badge_html}</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:20px">
            <div class="portal-stat">
                <div style="font-size:22px;font-weight:700;font-family:'JetBrains Mono',monospace">{latest_co2}</div>
                <div style="font-size:11px;opacity:.6">CO₂ ppm</div>
            </div>
            <div class="portal-stat">
                <div style="font-size:22px;font-weight:700;font-family:'JetBrains Mono',monospace">{latest_ch4}</div>
                <div style="font-size:11px;opacity:.6">CH₄ ppm</div>
            </div>
            <div class="portal-stat">
                <div style="font-size:22px;font-weight:700;font-family:'JetBrains Mono',monospace">{sum(1 for a in my_alerts if not a[3])}</div>
                <div style="font-size:11px;opacity:.6">Active alerts</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    ep1, ep2 = st.tabs(["📡 My Readings", "🚨 My Alerts"])
    with ep1:
        if my_readings:
            rdf = pd.DataFrame(my_readings, columns=["CO₂ (ppm)", "CH₄ (ppm)", "Timestamp"])
            st.dataframe(rdf, width="stretch")
            st.download_button("⬇️ Download", rdf.to_csv(index=False).encode(),
                               f"readings_{date.today()}.csv", "text/csv")
        else:
            st.info("No readings yet for your facility.")
    with ep2:
        if my_alerts:
            for atype, msg, ts, resolved in my_alerts:
                cls = "alert-critical" if atype == "Critical" else "alert-warning"
                icon = "🔴" if atype == "Critical" else "⚠️"
                st.markdown(f'<div class="{cls}"><strong>{icon} {atype}</strong> — {msg}<br>'
                            f'<small>{ts} · {"✅ Resolved" if resolved else "🔴 Active"}</small></div>',
                            unsafe_allow_html=True)
        else:
            st.markdown('<div class="alert-ok">✅ No alerts for your facility.</div>', unsafe_allow_html=True)
    st.stop()


# ══════════════════════════════════════════════════════════════
# SIDEBAR  (admin / officer)
# ══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown(f"""
    <div style="padding:22px 18px 18px;border-bottom:1px solid #1a3a25;margin-bottom:16px">
        <div style="font-size:20px;font-weight:700">🌿 GHG Monitor</div>
        <div style="font-size:10px;opacity:.5;margin-top:2px;letter-spacing:.06em;text-transform:uppercase">Makoni District · EMA</div>
    </div>
    <div style="background:rgba(46,184,114,0.08);border:1px solid rgba(46,184,114,0.18);border-radius:12px;padding:12px 14px;margin-bottom:18px">
        <div style="font-size:10.5px;opacity:.5;letter-spacing:.07em;text-transform:uppercase;margin-bottom:5px">
            {"🛡 District Officer" if is_admin else "👤 Field Officer"}
        </div>
        <div style="font-size:14px;font-weight:600">{user['full_name']}</div>
        <div style="font-size:11px;opacity:.5;margin-top:3px">Since {st.session_state.get('session_start', '')}</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<p style="font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#3a6e52;margin-bottom:10px">⚙ Controls</p>',
                unsafe_allow_html=True)
    auto_refresh = st.toggle("Auto Refresh (5s)", value=False)
    if st.button("🔄  Refresh Now"):
        st.rerun()
    st.markdown("<hr style='border:none;border-top:1px solid #1a3a25;margin:16px 0'>", unsafe_allow_html=True)
    st.markdown('<p style="font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#3a6e52;margin-bottom:10px">📏 EMA Thresholds</p>',
                unsafe_allow_html=True)
    st.markdown(f'<p style="font-size:13px">CO₂ limit: <strong style="color:#7dd9a8">{CO2_LIMIT} ppm</strong></p>', unsafe_allow_html=True)
    st.markdown(f'<p style="font-size:13px">CH₄ limit: <strong style="color:#7dd9a8">{CH4_LIMIT} ppm</strong></p>', unsafe_allow_html=True)
    st.markdown("<hr style='border:none;border-top:1px solid #1a3a25;margin:16px 0'>", unsafe_allow_html=True)
    if st.button("🚪  Logout"):
        for k in ["user", "logged_in", "session_start"]:
            st.session_state.pop(k, None)
        st.rerun()


# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════

registered_emitters = get_all_emitters()

col_hd1, col_hd2 = st.columns([3, 1])
with col_hd1:
    st.markdown('<p class="page-title">GHG Emissions Monitoring Dashboard</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="page-sub">Makoni District · Environmental Management Agency · ESP32 + MQ-4 + MQ-135 · {len(registered_emitters)} registered emitters</p>',
                unsafe_allow_html=True)
with col_hd2:
    st.markdown(f"""
    <div style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;color:#7a9e88;margin-top:6px">
        {datetime.now().strftime("%a, %d %b %Y")}<br>
        <strong style="color:#0a2a18;font-size:15px">{datetime.now().strftime("%H:%M:%S")}</strong>
    </div>""", unsafe_allow_html=True)

st.markdown("<div class='fancy-divider'></div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# ACQUIRE & PROCESS READINGS
# ══════════════════════════════════════════════════════════════

raw              = load_live_readings()
readings         = []
all_emitters_map = {e["id"]: e for e in registered_emitters}
live_columns     = ["Emitter", "Type", "CO₂ (ppm)", "CH₄ (ppm)", "Status", "Source", "_eid"]

for r in raw:
    co2, ch4     = r["co2"], r["ch4"]
    status       = classify(co2, ch4)
    emitter_full = all_emitters_map.get(r["id"], {})
    readings.append({
        "Emitter":   r["name"], "Type": r["type"],
        "CO₂ (ppm)": co2,      "CH₄ (ppm)": ch4,
        "Status":    status,   "Source": r["source"], "_eid": r["id"]
    })
    if r["source"] == "simulated":
        save_reading(r["id"], co2, ch4, user["id"])
    if status in ("Warning", "Critical"):
        save_alert(r["id"], status, f"{status}: CO₂={co2} ppm, CH₄={ch4} ppm")
    if status == "Critical":
        auto_notify_breach(emitter_full, co2, ch4, status)

df        = pd.DataFrame(readings, columns=live_columns)
compliant = int((df["Status"] == "Compliant").sum())
warning   = int((df["Status"] == "Warning").sum())
critical  = int((df["Status"] == "Critical").sum())
avg_co2   = 0.0 if df.empty else df["CO₂ (ppm)"].mean()
avg_ch4   = 0.0 if df.empty else df["CH₄ (ppm)"].mean()
data_src  = "📡 Live" if raw and raw[0]["source"] == "live" else "🎲 Simulated"


# ── KPI strip ─────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
kpis = [
    (c1, "Avg CO₂",   f"{avg_co2:.1f}", "ppm",
     f"{'↑' if avg_co2 > CO2_LIMIT else '↓'} {abs(avg_co2-CO2_LIMIT):.1f} vs limit",
     "kpi-delta-red" if avg_co2 > CO2_LIMIT else "kpi-delta-green",
     "#e53935" if avg_co2 > CO2_LIMIT else "#2eb872"),
    (c2, "Avg CH₄",   f"{avg_ch4:.1f}", "ppm",
     f"{'↑' if avg_ch4 > CH4_LIMIT else '↓'} {abs(avg_ch4-CH4_LIMIT):.1f} vs limit",
     "kpi-delta-red" if avg_ch4 > CH4_LIMIT else "kpi-delta-green",
     "#e53935" if avg_ch4 > CH4_LIMIT else "#2eb872"),
    (c3, "Compliant", str(compliant),  f"of {len(df)}", "", "kpi-delta-green", "#2eb872"),
    (c4, "Warning",   str(warning),    "emitters",      "", "kpi-delta-green", "#f5a623"),
    (c5, "Critical",  str(critical),   "emitters",      "", "kpi-delta-red",   "#e53935"),
    (c6, "Data",      data_src,        "source",        "", "kpi-delta-green", "#7a9e88"),
]
for col, label, val, unit, delta, delta_cls, accent in kpis:
    with col:
        st.markdown(f"""
        <div class="kpi-box">
            <div class="kpi-accent" style="background:{accent}"></div>
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{val}</div>
            <div class="kpi-unit">{unit}</div>
            {"<div class='kpi-delta "+delta_cls+"'>"+delta+"</div>" if delta else ""}
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════

tab_labels = ["📡 Live Readings", "📈 Trends", "🚨 Alerts", "📋 History", "⚖️ Compliance"]
if is_admin:
    tab_labels += ["⚙️ Admin"]
tabs = st.tabs(tab_labels)
tab_live, tab_trends, tab_alerts, tab_history, tab_compliance = tabs[:5]
tab_admin = tabs[5] if is_admin else None


# ══════════════════════════════════════════════════════════════
# TAB 1 — LIVE READINGS
# ══════════════════════════════════════════════════════════════
with tab_live:
    st.markdown(f'<p class="section-hdr">Real-time sensor data — all {len(registered_emitters)} emitters</p>', unsafe_allow_html=True)

    table_rows = ""
    for _, row in df.iterrows():
        s     = row["Status"]
        co2   = row["CO₂ (ppm)"]
        ch4   = row["CH₄ (ppm)"]
        badge = status_badge_html(s)
        b_co2 = bar_html(co2, CO2_LIMIT)
        b_ch4 = bar_html(ch4, CH4_LIMIT)
        is_road   = "Road" in str(row["Type"]) or "Street" in str(row["Type"])
        type_html = (f'<span class="badge badge-road">{row["Type"]}</span>' if is_road
                     else f'<span class="td-type">{row["Type"]}</span>')
        src_icon  = "📡" if row["Source"] == "live" else "🎲"
        table_rows += f"""
        <tr>
            <td class="td-name">{row['Emitter']}</td>
            <td>{type_html}</td>
            <td class="td-num">{co2}</td>
            <td style="padding:11px 14px;min-width:120px">{b_co2}</td>
            <td class="td-num">{ch4}</td>
            <td style="padding:11px 14px;min-width:120px">{b_ch4}</td>
            <td>{badge}</td>
            <td style="text-align:center;font-size:14px" title="{row['Source']}">{src_icon}</td>
        </tr>"""

    st.markdown(f"""
    <div class="ghg-card" style="padding:0;overflow:hidden">
        <table class="ghg-table">
            <thead><tr>
                <th>Emitter</th><th>Type</th>
                <th>CO₂ ppm</th><th>CO₂ load</th>
                <th>CH₄ ppm</th><th>CH₄ load</th>
                <th>Status</th><th title="Data source">Src</th>
            </tr></thead>
            <tbody>{table_rows}</tbody>
        </table>
    </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    ci1, ci2 = st.columns(2)
    with ci1:
        st.info(f"♻️ **Reduction potential (10% intervention):** {round(avg_co2 * 0.1, 1)} ppm CO₂")
    with ci2:
        csv_data = df.drop(columns=["_eid", "Source"]).to_csv(index=False).encode()
        st.download_button("⬇️ Download Live Readings CSV", csv_data,
                           f"ghg_live_{date.today()}.csv", "text/csv", width="stretch")


# ══════════════════════════════════════════════════════════════
# TAB 2 — TRENDS
# ══════════════════════════════════════════════════════════════
    st.markdown("<div class='fancy-divider'></div>", unsafe_allow_html=True)
    st.markdown('<p class="section-hdr">Latest 20 saved readings from database</p>', unsafe_allow_html=True)
    latest_df = load_latest_readings(20)
    if latest_df.empty:
        st.info("No saved readings yet.")
    else:
        st.dataframe(latest_df, width="stretch")


with tab_trends:
    st.markdown('<p class="section-hdr">Emissions trends & analytics</p>', unsafe_allow_html=True)

    tr1, tr2 = st.columns(2)
    with tr1:
        st.markdown('<div class="ghg-card"><div class="ghg-card-title">CO₂ Emissions by Emitter</div>', unsafe_allow_html=True)
        st.bar_chart(df.set_index("Emitter")[["CO₂ (ppm)"]], color="#2eb872", height=260)
        st.markdown("</div>", unsafe_allow_html=True)
    with tr2:
        st.markdown('<div class="ghg-card"><div class="ghg-card-title">CH₄ Emissions by Emitter</div>', unsafe_allow_html=True)
        st.bar_chart(df.set_index("Emitter")[["CH₄ (ppm)"]], color="#f5a623", height=260)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="ghg-card"><div class="ghg-card-title">CO₂ vs CH₄ Comparison — all emitters</div>', unsafe_allow_html=True)
    st.bar_chart(df.set_index("Emitter")[["CO₂ (ppm)", "CH₄ (ppm)"]], height=300)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='fancy-divider'></div>", unsafe_allow_html=True)
    st.markdown('<p class="section-hdr">Historical statistics</p>', unsafe_allow_html=True)
    dc1, dc2 = st.columns(2)
    with dc1:
        start = st.date_input("From", value=date.today() - timedelta(days=30))
    with dc2:
        end = st.date_input("To", value=date.today())

    stats = get_emissions_statistics(str(start), str(end))
    if stats:
        sdf = pd.DataFrame(stats, columns=[
            "Emitter", "Avg CO₂", "Max CO₂", "Min CO₂",
            "Avg CH₄", "Max CH₄", "Min CH₄", "Readings", "Total CO₂", "Total CH₄"
        ])
        st.dataframe(sdf.round(2), width="stretch")
        comp  = get_compliance_statistics(str(start), str(end))
        total = sum(comp.values()) or 1
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Compliant Readings", comp["compliant"], f"{comp['compliant']/total*100:.0f}%")
        sc2.metric("Warning Readings",   comp["warning"],   f"{comp['warning']/total*100:.0f}%")
        sc3.metric("Critical Readings",  comp["critical"],  f"{comp['critical']/total*100:.0f}%")
    else:
        st.info("No historical readings for this period.")


# ══════════════════════════════════════════════════════════════
# TAB 3 — ALERTS
# ══════════════════════════════════════════════════════════════
with tab_alerts:
    st.markdown('<p class="section-hdr">Active threshold alerts</p>', unsafe_allow_html=True)

    crit_df = df[df["Status"] == "Critical"]
    warn_df = df[df["Status"] == "Warning"]

    if crit_df.empty and warn_df.empty:
        st.markdown('<div class="alert-ok">✅ <strong>All clear</strong> — all emitters within compliant levels.</div>',
                    unsafe_allow_html=True)
    else:
        for _, row in crit_df.iterrows():
            strats = get_strategies(row["CO₂ (ppm)"], row["CH₄ (ppm)"])
            bc     = get_breach_count(row["_eid"])
            exc    = max((row["CO₂ (ppm)"] - CO2_LIMIT) / CO2_LIMIT * 100,
                         (row["CH₄ (ppm)"] - CH4_LIMIT) / CH4_LIMIT * 100)
            pen    = suggest_penalty(bc, exc)
            st.markdown(f"""
            <div class="alert-critical">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                    <strong>🔴 CRITICAL — {row['Emitter']}</strong>
                    <span class="auto-badge">⚡ auto-notified</span>
                </div>
                CO₂: <code>{row['CO₂ (ppm)']} ppm</code> · CH₄: <code>{row['CH₄ (ppm)']} ppm</code>
                · Unresolved breaches: <strong>{bc}</strong><br>
                <small>Actions: {" · ".join(strats)}</small><br>
                <small>💼 Suggested penalty: <strong>{pen['level']}</strong>
                {"— $" + str(pen['amount']) if pen['amount'] else ""} ({pen['reason']})</small>
            </div>""", unsafe_allow_html=True)

        for _, row in warn_df.iterrows():
            st.markdown(f"""
            <div class="alert-warning">
                <strong>⚠️ WARNING — {row['Emitter']}</strong><br>
                CO₂: <code>{row['CO₂ (ppm)']} ppm</code> · CH₄: <code>{row['CH₄ (ppm)']} ppm</code>
            </div>""", unsafe_allow_html=True)

    st.markdown("<div class='fancy-divider'></div>", unsafe_allow_html=True)
    st.markdown('<p class="section-hdr">Unresolved alerts (database)</p>', unsafe_allow_html=True)
    db_alerts = get_all_alerts()
    if db_alerts:
        adf = pd.DataFrame(db_alerts, columns=["ID", "Emitter", "Type", "Message", "Timestamp", "Resolved"])
        st.dataframe(adf.drop(columns=["Resolved"]), width="stretch")
        if is_admin:
            al1, al2 = st.columns([1, 2])
            with al1:
                alert_id = st.number_input("Alert ID to resolve", min_value=1, step=1)
            with al2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅ Mark Resolved"):
                    resolve_alert(int(alert_id), user["id"])
                    st.success(f"Alert #{alert_id} resolved.")
                    st.rerun()
    else:
        st.info("No unresolved alerts in the database.")


# ══════════════════════════════════════════════════════════════
# TAB 4 — HISTORY
# ══════════════════════════════════════════════════════════════
with tab_history:
    st.markdown('<p class="section-hdr">Historical emission readings</p>', unsafe_allow_html=True)
    hc1, hc2 = st.columns(2)
    with hc1:
        h_start = st.date_input("From date", value=date.today() - timedelta(days=7), key="h_start")
    with hc2:
        h_end = st.date_input("To date", value=date.today(), key="h_end")

    history = get_readings_by_date_range(str(h_start), str(h_end))
    if history:
        hdf = pd.DataFrame(history, columns=["ID", "Emitter", "CO₂ (ppm)", "CH₄ (ppm)", "Timestamp", "Recorded By"])
        st.markdown(f"**{len(hdf)} readings found**")
        st.dataframe(hdf, width="stretch")
        st.download_button("⬇️ Download CSV", hdf.to_csv(index=False).encode(),
                           f"ghg_history_{h_start}_{h_end}.csv", "text/csv")
    else:
        all_hist = get_all_readings()
        if all_hist:
            st.info("No readings in selected range. Showing all available.")
            st.dataframe(
                pd.DataFrame(all_hist, columns=["ID", "Emitter", "CO₂ (ppm)", "CH₄ (ppm)", "Timestamp", "Recorded By"]),
                width="stretch"
            )
        else:
            st.info("No readings yet. Data accumulates with each refresh.")


# ══════════════════════════════════════════════════════════════
# TAB 5 — COMPLIANCE
# ══════════════════════════════════════════════════════════════
with tab_compliance:
    st.markdown('<p class="section-hdr">Compliance actions & penalty engine</p>', unsafe_allow_html=True)

    emitters_list = get_all_emitters()
    emitter_names = [e["name"] for e in emitters_list]

    cc1, cc2 = st.columns(2)

    with cc1:
        st.markdown('<div class="ghg-card">', unsafe_allow_html=True)
        st.markdown('<div class="ghg-card-title">⚡ Auto-suggested penalties (this session)</div>', unsafe_allow_html=True)
        has_suggestions = False
        for _, row in df[df["Status"] == "Critical"].iterrows():
            bc  = get_breach_count(row["_eid"])
            exc = max(
                (row["CO₂ (ppm)"] - CO2_LIMIT) / CO2_LIMIT * 100,
                (row["CH₄ (ppm)"] - CH4_LIMIT) / CH4_LIMIT * 100
            )
            pen = suggest_penalty(bc, exc)
            if pen["level"] != "None":
                has_suggestions = True
                st.markdown(f"""
                <div style="background:#fffbf0;border:1px solid #ffe082;border-radius:10px;padding:12px 14px;margin-bottom:8px">
                    <strong style="color:#0a2a18">{row['Emitter']}</strong><br>
                    <span style="font-size:12px;color:#7a4f00">
                        Suggested: <strong>{pen['level']}</strong>
                        {"— $" + str(pen['amount']) if pen['amount'] else ""}<br>
                        Reason: {pen['reason']}
                    </span>
                </div>""", unsafe_allow_html=True)
        if not has_suggestions:
            st.info("No suggestions — no critical emitters this session.")
        st.markdown("</div>", unsafe_allow_html=True)

    with cc2:
        st.markdown('<div class="ghg-card">', unsafe_allow_html=True)
        st.markdown('<div class="ghg-card-title">Log a compliance action</div>', unsafe_allow_html=True)
        with st.form("compliance_form"):
            ca_emitter = st.selectbox("Emitter", emitter_names)
            ca1, ca2   = st.columns(2)
            ca_type    = ca1.selectbox("Alert Type",    ["Warning", "Critical"])
            ca_penalty = ca2.selectbox("Penalty Level", ["Notice", "Fine", "Suspension", "Closure"])
            ca3, ca4   = st.columns(2)
            ca_amount  = ca3.number_input("Penalty Amount (USD)", min_value=0.0, step=50.0)
            ca_notif   = ca4.selectbox("Notification",  ["Email", "SMS", "Physical Letter", "WhatsApp"])
            ca_action  = st.text_area("Action Taken", height=80)
            ca_report  = st.checkbox("Report Sent to Emitter")
            if st.form_submit_button("Log Action", width="stretch", type="primary"):
                em = get_emitter_by_name(ca_emitter)
                if em:
                    add_compliance_action(em["id"], ca_type, ca_penalty, ca_amount,
                                          ca_action, ca_report, ca_notif)
                    st.success("Compliance action logged.")
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='fancy-divider'></div>", unsafe_allow_html=True)
    actions = get_all_compliance_actions()
    if actions:
        adf = pd.DataFrame(actions, columns=[
            "ID", "Emitter", "Alert Type", "Penalty Level",
            "Amount (USD)", "Action Taken", "Report Sent", "Notification", "Date"
        ])
        st.dataframe(adf, width="stretch")
        st.download_button("⬇️ Export Compliance Log", adf.to_csv(index=False).encode(),
                           "compliance_log.csv", "text/csv")
    else:
        st.info("No compliance actions logged yet.")


# ══════════════════════════════════════════════════════════════
# TAB 6 — ADMIN
# ══════════════════════════════════════════════════════════════
if is_admin and tab_admin is not None:
    with tab_admin:
        st.markdown('<p class="section-hdr">Administration panel — District Officer</p>', unsafe_allow_html=True)

        atab1, atab2, atab3, atab4, atab5 = st.tabs(
            ["👥 Users", "🏭 Emitters", "🔑 Security", "📧 Reports & Notifications", "⚙️ Settings"]
        )

        # ── Users ──────────────────────────────────────────────
        with atab1:
            st.markdown("**Registered system users**")
            users_all = get_all_users()
            udf = pd.DataFrame(users_all)
            if not udf.empty:
                udf["is_active"] = udf["is_active"].map({1: "✅ Active", 0: "❌ Inactive"})
                st.dataframe(
                    udf[["id","full_name","username","role","email","phone",
                          "created_at","last_login","is_active"]],
                    width="stretch"
                )
            st.divider()
            st.markdown("**Create new user**")
            with st.form("add_user_form"):
                u1, u2    = st.columns(2)
                new_role  = u1.selectbox("Role", ["officer", "emitter", "admin"])
                new_name  = u2.text_input("Full Name")
                u3, u4    = st.columns(2)
                new_uname = u3.text_input("Username")
                new_pass  = u4.text_input("Password", type="password")
                u5, u6    = st.columns(2)
                new_email = u5.text_input("Email")
                new_phone = u6.text_input("Phone")
                emitter_id = None
                if new_role == "emitter":
                    all_em = get_all_emitters()
                    sel    = st.selectbox("Assign to Emitter", [e["name"] for e in all_em])
                    emitter_id = next((e["id"] for e in all_em if e["name"] == sel), None)
                if st.form_submit_button("Create User", width="stretch", type="primary"):
                    if not (new_name and new_uname and new_pass):
                        st.error("Name, username and password are required.")
                    else:
                        ok, msg = is_strong_password(new_pass)
                        if not ok:
                            st.error(msg)
                        else:
                            try:
                                add_user(new_name, new_uname, new_pass, new_role,
                                         new_email, new_phone, emitter_id)
                                st.success(f"User '{new_uname}' created.")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Error: {ex}")
            st.divider()
            st.markdown("**Toggle user active status**")
            t1, t2, t3 = st.columns(3)
            tog_id = t1.number_input("User ID", min_value=1, step=1)
            tog_st = t2.selectbox("Set Status", ["Active", "Inactive"])
            t3.markdown("<br>", unsafe_allow_html=True)
            if t3.button("Apply", width="stretch"):
                toggle_user_active(int(tog_id), tog_st == "Active")
                st.success(f"User #{tog_id} → {tog_st}.")
                st.rerun()

        # ── Emitters ────────────────────────────────────────────
            st.divider()
            st.markdown("**Delete user**")
            if users_all:
                delete_options = {
                    f"{u['id']} - {u['full_name']} ({u['username']}, {u['role']})": u["id"]
                    for u in users_all
                    if u["id"] != user["id"]
                }
                if delete_options:
                    with st.form("delete_user_form"):
                        selected_user = st.selectbox("User to delete", list(delete_options.keys()))
                        confirm_delete = st.checkbox("I understand this permanently deletes the selected user account.")
                        if st.form_submit_button("Delete User", width="stretch"):
                            if not confirm_delete:
                                st.error("Confirm deletion before continuing.")
                            else:
                                ok, msg = delete_user(delete_options[selected_user], user["id"])
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                else:
                    st.info("There are no other users available to delete.")
            else:
                st.info("No users available.")

        with atab2:
            st.markdown(f"**All {len(get_all_emitters())} registered emitters**")
            st.dataframe(pd.DataFrame(get_all_emitters()), width="stretch")
            st.divider()
            st.markdown("**Register new emitter + portal account**")
            with st.form("new_emitter_portal"):
                e1, e2  = st.columns(2)
                em_name = e1.text_input("Facility Name")
                em_type = e2.selectbox("Type", ["Incinerator","Generator","Combustion","Agriculture",
                                                  "Wetland","Transport","Road/Street","Waste/Landfill","Other"])
                e3, e4  = st.columns(2)
                em_loc  = e3.text_input("Location")
                em_cont = e4.text_input("Contact Person")
                e5, e6  = st.columns(2)
                em_ph   = e5.text_input("Contact Phone")
                em_em   = e6.text_input("Contact Email")
                st.markdown("---")
                ep1, ep2 = st.columns(2)
                em_user  = ep1.text_input("Portal Username")
                em_pass  = ep2.text_input("Portal Password", type="password")
                if st.form_submit_button("Create Emitter + Portal", width="stretch", type="primary"):
                    if not em_name:
                        st.error("Facility name is required.")
                    elif not em_user or not em_pass:
                        st.error("Portal credentials are required.")
                    else:
                        try:
                            register_emitter_with_portal(em_name, em_type, em_loc, em_cont,
                                                          em_ph, em_em, user["id"], em_user, em_pass)
                            st.success("Emitter and portal account created.")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Error: {ex}")
            st.divider()
            st.markdown("**Register emitter only (no portal login)**")
            with st.form("emitter_only_form"):
                f1, f2 = st.columns(2)
                fn = f1.text_input("Facility Name",   key="fn2")
                ft = f2.selectbox("Type", ["Incinerator","Generator","Combustion","Agriculture",
                                            "Wetland","Transport","Road/Street","Waste/Landfill","Other"], key="ft2")
                f3, f4 = st.columns(2)
                fl = f3.text_input("Location",        key="fl2")
                fc = f4.text_input("Contact Person",  key="fc2")
                f5, f6 = st.columns(2)
                fp = f5.text_input("Contact Phone",   key="fp2")
                fe = f6.text_input("Contact Email",   key="fe2")
                if st.form_submit_button("Register Emitter", width="stretch"):
                    if not fn:
                        st.error("Facility name is required.")
                    else:
                        conn = get_connection()
                        cur  = conn.cursor()
                        try:
                            cur.execute("""
                                INSERT INTO emitters
                                    (name,type,location,contact_person,contact_phone,contact_email,added_by,added_at)
                                VALUES (?,?,?,?,?,?,?,?)
                            """, (fn, ft, fl, fc, fp, fe, user["id"],
                                  datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                            conn.commit()
                            st.success(f"'{fn}' registered.")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Error: {ex}")
                        finally:
                            conn.close()

        # ── Security ────────────────────────────────────────────
        with atab3:
            st.markdown("**Change your password**")
            with st.form("chg_pass_form"):
                old_p  = st.text_input("Current Password", type="password")
                new_p1 = st.text_input("New Password",     type="password")
                new_p2 = st.text_input("Confirm Password", type="password")
                if st.form_submit_button("Update Password", width="stretch", type="primary"):
                    if "error" in verify_login(user["username"], old_p):
                        st.error("Current password is incorrect.")
                    elif new_p1 != new_p2:
                        st.error("Passwords do not match.")
                    else:
                        ok, msg = is_strong_password(new_p1)
                        if not ok:
                            st.error(msg)
                        else:
                            change_password(user["id"], new_p1)
                            st.success("Password updated successfully.")
            st.divider()
            st.markdown("**Password policy:** Min 8 chars · 1 uppercase · 1 digit · 1 special character")

        # ── Reports & Notifications ─────────────────────────────
        with atab4:
            st.markdown("**SMTP / SMS notification settings**")
            notif = get_notification_settings()
            with st.form("notif_form"):
                n1, n2    = st.columns(2)
                smtp_host = n1.text_input("SMTP Host",     value=notif["smtp_host"])
                smtp_port = n2.number_input("SMTP Port",   value=notif["smtp_port"], min_value=1, max_value=65535)
                n3, n4    = st.columns(2)
                smtp_user = n3.text_input("SMTP Username", value=notif["smtp_user"])
                smtp_pass = n4.text_input("SMTP Password", value=notif["smtp_pass"], type="password")
                n5, n6    = st.columns(2)
                smtp_from = n5.text_input("Sender Email",  value=notif["smtp_from"])
                sms_gw    = n6.text_input("SMS Gateway",   value=notif["sms_gateway"],
                                           help="e.g. sms.econet.co.zw")
                if st.form_submit_button("Save Settings", width="stretch", type="primary"):
                    save_notification_settings({
                        "smtp_host": smtp_host, "smtp_port": smtp_port,
                        "smtp_user": smtp_user, "smtp_pass": smtp_pass,
                        "smtp_from": smtp_from, "sms_gateway": sms_gw,
                    })
                    st.success("Notification settings saved.")

            st.divider()
            notif  = get_notification_settings()
            report = build_report(df)
            s      = report["summary"]
            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("Total Emitters", s["total_emitters"])
            rc2.metric("✅ Compliant",   s["compliant"])
            rc3.metric("⚠️ Warning",     s["warning"])
            rc4.metric("🔴 Critical",    s["critical"])
            st.markdown(f"Avg CO₂: **{s['avg_co2']} ppm** · Avg CH₄: **{s['avg_ch4']} ppm** · {s['generated_at']}")
            st.download_button("⬇️ Download Compliance Report CSV", report["csv"],
                               "compliance_report.csv", "text/csv", width="stretch")
            st.divider()
            with st.form("send_report_form"):
                recipient    = st.text_input("Recipient Email",
                                              value=notif["smtp_from"] or user.get("email", ""))
                sms_emitters = st.checkbox("SMS to all emitter contacts", value=True)
                sms_officer  = st.checkbox("SMS to my phone",             value=True)
                if st.form_submit_button("Send Report", width="stretch", type="primary"):
                    if not all([notif["smtp_host"], notif["smtp_user"],
                                notif["smtp_pass"], notif["smtp_from"]]):
                        st.error("Configure SMTP settings first.")
                    elif not recipient:
                        st.error("Enter a recipient email.")
                    else:
                        try:
                            send_email_message(
                                notif["smtp_host"], int(notif["smtp_port"]),
                                notif["smtp_user"], notif["smtp_pass"], notif["smtp_from"],
                                recipient, "GHG Compliance Report — Makoni District",
                                f"Compliance summary:\n{s}\n\nFull CSV available in the dashboard."
                            )
                            st.success(f"Report emailed to {recipient}.")
                            if sms_emitters and notif["sms_gateway"]:
                                sent_sms = 0
                                failed_sms = []
                                for em in get_all_emitters():
                                    if em.get("contact_phone"):
                                        try:
                                            send_sms_via_gateway(
                                                notif["smtp_host"], int(notif["smtp_port"]),
                                                notif["smtp_user"], notif["smtp_pass"],
                                                notif["smtp_from"], em["contact_phone"],
                                                notif["sms_gateway"],
                                                f"GHG Report: {s['critical']} critical, {s['warning']} warning. {s['generated_at']}"
                                            )
                                            sent_sms += 1
                                        except Exception as sms_ex:
                                            failed_sms.append(f"{em.get('name', 'Unknown')}: {sms_ex}")
                                if sent_sms:
                                    st.info(f"SMS sent to {sent_sms} emitter contact(s).")
                                if failed_sms:
                                    st.warning("Some SMS messages failed:\n" + "\n".join(failed_sms[:5]))
                            if sms_officer and user.get("phone") and notif["sms_gateway"]:
                                send_sms_via_gateway(
                                    notif["smtp_host"], int(notif["smtp_port"]),
                                    notif["smtp_user"], notif["smtp_pass"], notif["smtp_from"],
                                    user["phone"], notif["sms_gateway"],
                                    f"Report sent. Critical: {s['critical']}, Warning: {s['warning']}"
                                )
                                st.info("SMS sent to your phone.")
                        except Exception as ex:
                            st.error(f"Failed to send: {ex}")

            st.divider()
            ca = get_all_compliance_actions()
            if ca:
                st.dataframe(
                    pd.DataFrame(ca, columns=["ID","Emitter","Alert Type","Penalty Level",
                                               "Penalty Amount","Action","Report Sent","Method","Created At"]),
                    width="stretch"
                )

        # ── Settings ────────────────────────────────────────────
        with atab5:
            st.markdown("**Application settings**")
            settings = get_all_settings()
            with st.form("settings_form"):
                s1 = st.text_input("Organisation Name", value=settings.get("org_name", "EMA Makoni District"))
                s2 = st.text_input("District",          value=settings.get("district",  "Makoni"))
                sc1, sc2 = st.columns(2)
                s3 = sc1.number_input("CO₂ Threshold (ppm)",
                                       value=float(settings.get("co2_limit", CO2_LIMIT)), step=10.0)
                s4 = sc2.number_input("CH₄ Threshold (ppm)",
                                       value=float(settings.get("ch4_limit", CH4_LIMIT)), step=1.0)
                if st.form_submit_button("Save Settings", width="stretch", type="primary"):
                    set_setting("org_name", s1); set_setting("district", s2)
                    set_setting("co2_limit", str(s3)); set_setting("ch4_limit", str(s4))
                    st.success("Settings saved.")


# ══════════════════════════════════════════════════════════════
# AUTO-REFRESH + FOOTER
# ══════════════════════════════════════════════════════════════
if auto_refresh:
    time.sleep(5)
    st.rerun()

st.markdown(f"""
<div style="text-align:center;padding:24px 0 10px;margin-top:32px;
     border-top:1px solid #e2ede8;font-size:11px;color:#7a9e88;
     font-family:'JetBrains Mono',monospace">
     · Makoni District GHG Monitoring · EMA ® © 2026 ·
    {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ·
    Logged in as <strong style="color:#0a2a18">{user['username']}</strong>
</div>
""", unsafe_allow_html=True)
