import os, io, sqlite3, secrets, hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
import qrcode

APP_TITLE = "Can You Beat the Crowd?"
DB_PATH = os.getenv("CROWD_DB_PATH", "crowd_guesses.db")
QUESTIONS = {
    "tower": {"title": "How tall is the CN Tower?", "unit": "metres", "actual": 553.3, "actual_display": "553.3 metres"},
    "moon": {"title": "How far away is the Moon from Earth?", "unit": "kilometres", "actual": 384400, "actual_display": "384,400 kilometres on average"},
    "piano": {"title": "How many keys does a regular piano have?", "unit": "keys", "actual": 88, "actual_display": "88 keys"},
}

st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="wide")

def db():
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            tower REAL NOT NULL, moon REAL NOT NULL, piano REAL NOT NULL,
            submitted_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        )""")
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('revealed','0')")

def setting(key, default="0"):
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def set_setting(key, value):
    with db() as conn:
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

def get_data():
    with db() as conn:
        rows = conn.execute("SELECT tower,moon,piano,submitted_at FROM submissions ORDER BY id").fetchall()
    return pd.DataFrame([dict(r) for r in rows])

def qr_bytes(url):
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()

init_db()

st.markdown("""
<style>
.block-container {max-width: 1100px; padding-top: 1.6rem;}
.hero {padding: 1.4rem; border-radius: 16px; background: linear-gradient(135deg,#102a43,#243b53); color:white;}
.hero h1 {color:white; margin-bottom:.3rem;}
.hero p {color:#e5edf5; margin:0;}
div[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.25); padding:12px; border-radius:12px;}
.question-card {margin-top:1rem; padding:1rem 1.1rem .5rem; border-radius:14px; background:rgba(100,116,139,.12); border:1px solid rgba(128,128,128,.22);}
.question-title {font-size:1.15rem; font-weight:700; margin-bottom:.25rem;}
.answer-card {margin:.35rem 0 .65rem; padding:1rem 1.1rem; border-radius:14px; background:rgba(16,185,129,.10); border:1px solid rgba(16,185,129,.35);}
.answer-label {font-size:.85rem; opacity:.8;}
.answer-value {font-size:1.45rem; font-weight:750; margin-top:.15rem;}
</style>
""", unsafe_allow_html=True)

st.markdown(f'<div class="hero"><h1>🎯 {APP_TITLE}</h1><p>VentureLAB staff huddle · Three questions · One crowd</p></div>', unsafe_allow_html=True)
st.write("")

with st.sidebar:
    st.header("Navigation")
    page = st.radio("Open page", ["Submit guesses", "Live results", "Host controls"])

if page == "Submit guesses":
    st.subheader("Make your best estimates")
    st.write("No email or account is required. Enter your own estimates, then submit once.")
    if "participant_token" not in st.session_state:
        st.session_state.participant_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(st.session_state.participant_token.encode()).hexdigest()
    with db() as conn:
        existing = conn.execute("SELECT id FROM submissions WHERE token_hash=?", (token_hash,)).fetchone()

    if existing:
        st.success("Your guesses have already been submitted from this browser. Thanks for playing!")
    else:
        with st.form("guesses"):
