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
</style>
""", unsafe_allow_html=True)

st.markdown(f'<div class="hero"><h1>🎯 {APP_TITLE}</h1><p>VentureLAB staff huddle · Three questions · One crowd</p></div>', unsafe_allow_html=True)
st.write("")

with st.sidebar:
    st.header("Navigation")
    page = st.radio("Open page", ["Submit guesses", "Live results", "Host controls"])

if page == "Submit guesses":
    st.subheader("Make your best estimates")
    st.write("No email or account is required. Submit one set of guesses from this browser.")
    if "participant_token" not in st.session_state:
        st.session_state.participant_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(st.session_state.participant_token.encode()).hexdigest()
    with db() as conn:
        existing = conn.execute("SELECT id FROM submissions WHERE token_hash=?", (token_hash,)).fetchone()

    if existing:
        st.success("Your guesses have already been submitted from this browser. Thanks for playing!")
    else:
        with st.form("guesses"):
            c1, c2 = st.columns(2)
            with c1:
                tower = st.number_input("1. How tall is the CN Tower? (metres)", min_value=0.1, value=500.0, step=1.0)
                moon = st.number_input("2. How far away is the Moon? (kilometres)", min_value=1.0, value=400000.0, step=100.0)
            with c2:
                piano = st.number_input("3. How many keys does a regular piano have?", min_value=1, max_value=300, value=90, step=1)
                st.info("Estimate the average Earth–Moon distance for question 2.")
            submitted = st.form_submit_button("Submit my guesses", type="primary", use_container_width=True)
        if submitted:
            try:
                with db() as conn:
                    conn.execute("INSERT INTO submissions(token_hash,tower,moon,piano,submitted_at) VALUES(?,?,?,?,?)",
                        (token_hash, float(tower), float(moon), int(piano), datetime.now(timezone.utc).isoformat(timespec="seconds")))
                st.success("Your guesses are in. Thanks for playing!")
                st.balloons()
            except sqlite3.IntegrityError:
                st.info("A submission has already been recorded from this browser.")
    st.caption("Please submit only once. The host will reveal the answers after everyone has answered.")

elif page == "Live results":
    st.subheader("Live results")
    st.caption("Refresh this page to see the latest submissions.")
    data = get_data()
    st.metric("Total submissions", len(data))
    if data.empty:
        st.info("No guesses have been submitted yet.")
    else:
        cols = st.columns(3)
        for col, key in zip(cols, QUESTIONS):
            q = QUESTIONS[key]
            vals = pd.to_numeric(data[key], errors="coerce").dropna()
            with col:
                st.markdown(f"**{q['title']}**")
                st.metric("Mean", f"{vals.mean():,.1f} {q['unit']}")
                st.metric("Median", f"{vals.median():,.1f} {q['unit']}")
                st.caption(f"Guesses counted: {len(vals)}")
        if setting("revealed") == "1":
            st.divider()
            st.subheader("Answer reveal and closest guesses")
            for key, q in QUESTIONS.items():
                vals = pd.to_numeric(data[key], errors="coerce").dropna()
                st.markdown(f"**{q['title']}**")
                st.write(f"Actual answer: **{q['actual_display']}**")
                if not vals.empty:
                    diff = (vals - q["actual"]).abs()
                    min_diff = diff.min()
                    winners = vals[diff == min_diff].tolist()
                    winner_text = ", ".join(f"{v:,.1f}" for v in winners)
                    st.write(f"Closest guess(es): **{winner_text} {q['unit']}** — difference: {min_diff:,.1f} {q['unit']}")
        else:
            st.info("The host has not revealed the correct answers yet.")
        with st.expander("Anonymized submissions"):
            view = data[["tower", "moon", "piano"]].copy()
            view.columns = ["CN Tower (m)", "Moon distance (km)", "Piano keys"]
            st.dataframe(view, use_container_width=True, hide_index=True)

elif page == "Host controls":
    st.subheader("Host controls")
    st.warning("Starter version: this page is not password-protected. Anyone who can access the app can open these controls.")
    if setting("revealed") == "1":
        st.success("Correct answers are revealed.")
        if st.button("Hide correct answers", use_container_width=True):
            set_setting("revealed", "0")
            st.rerun()
    else:
        st.info("Correct answers are hidden.")
        if st.button("Reveal correct answers", type="primary", use_container_width=True):
            set_setting("revealed", "1")
            st.rerun()

    st.divider()
    st.subheader("Generate participant QR code")
    url = st.text_input("Public app URL", placeholder="https://your-app-name.streamlit.app")
    if url.strip():
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            st.error("Enter a full URL beginning with https:// or http://.")
        else:
            image = qr_bytes(url.strip())
            st.image(image, caption="Scan to open the app", width=260)
            st.download_button("Download QR code (PNG)", data=image, file_name="venturelab_icebreaker_qr.png", mime="image/png")
    st.divider()
    st.subheader("Export or reset")
    data = get_data()
    if not data.empty:
        st.download_button("Download responses (CSV)", data=data.to_csv(index=False).encode("utf-8"), file_name="venturelab_icebreaker_responses.csv", mime="text/csv")
        if "confirm_delete" not in st.session_state:
            st.session_state.confirm_delete = False
        if st.button("Prepare to delete all submissions"):
            st.session_state.confirm_delete = True
        if st.session_state.confirm_delete:
            ok = st.checkbox("I understand this permanently deletes all submissions.")
            if st.button("Confirm delete", disabled=not ok):
                with db() as conn:
                    conn.execute("DELETE FROM submissions")
                st.session_state.confirm_delete = False
                st.success("Submissions deleted.")
                st.rerun()
    else:
        st.caption("No submissions to export yet.")

st.divider()
st.caption("Answer references: CN Tower 553.3 m including antenna; average Earth–Moon distance about 384,400 km; standard piano 88 keys.")
