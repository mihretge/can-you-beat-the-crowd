import os
import io
import sqlite3
import secrets
import hashlib
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import qrcode

APP_TITLE = "Can You Beat the Crowd?"
DB_PATH = os.getenv("CROWD_DB_PATH", "crowd_guesses.db")

QUESTIONS = {
    "tower": {
        "title": "How tall is the CN Tower?",
        "unit": "metres",
        "actual": 553.3,
        "actual_display": "553.3 metres",
    },
    "moon": {
        "title": "How far away is the Moon from Earth?",
        "unit": "kilometres",
        "actual": 384400.0,
        "actual_display": "384,400 kilometres on average",
    },
    "piano": {
        "title": "How many keys does a regular piano have?",
        "unit": "keys",
        "actual": 88.0,
        "actual_display": "88 keys",
    },
}

st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="wide")


def db():
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                tower REAL NOT NULL,
                moon REAL NOT NULL,
                piano REAL NOT NULL,
                submitted_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES('revealed', '0')"
        )


def setting(key, default="0"):
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with db() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )


def get_data():
    with db() as conn:
        rows = conn.execute(
            "SELECT tower, moon, piano, submitted_at FROM submissions ORDER BY id"
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def qr_bytes(url):
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def host_is_authenticated():
    return bool(st.session_state.get("host_authenticated", False))


init_db()

st.markdown(
    """
    <style>
    .block-container {max-width: 1100px; padding-top: 1.6rem;}
    .hero {padding: 1.4rem; border-radius: 16px;
           background: linear-gradient(135deg,#102a43,#243b53); color:white;}
    .hero h1 {color:white; margin-bottom:.3rem;}
    .hero p {color:#e5edf5; margin:0;}
    div[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.25);
                                  padding:12px; border-radius:12px;}
    .answer-card {margin:.35rem 0 .65rem; padding:1rem 1.1rem;
                  border-radius:14px; background:rgba(16,185,129,.10);
                  border:1px solid rgba(16,185,129,.35);}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f'<div class="hero"><h1>🎯 {APP_TITLE}</h1>'
    "<p>VentureLAB staff huddle · Three questions · One crowd</p></div>",
    unsafe_allow_html=True,
)
st.write("")

with st.sidebar:
    st.header("Navigation")
    page = st.radio(
        "Open page",
        ["Submit guesses", "Live results", "Host controls"],
    )

if page == "Submit guesses":
    st.subheader("Make your best estimates")
    st.write(
        "No email or account is required. Enter your own estimates, then submit once."
    )

    if "participant_token" not in st.session_state:
        st.session_state.participant_token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        st.session_state.participant_token.encode()
    ).hexdigest()

    with db() as conn:
        existing = conn.execute(
            "SELECT id FROM submissions WHERE token_hash = ?", (token_hash,)
        ).fetchone()

    if existing:
        st.success(
            "Your guesses have already been submitted from this browser. Thanks for playing!"
        )
    else:
        with st.form("guesses"):
            tower = st.number_input(
                "1. How tall is the CN Tower? (metres)",
                min_value=0.0,
                value=None,
                placeholder="Enter your estimate",
                step=1.0,
                format="%.1f",
            )
            moon = st.number_input(
                "2. How far away is the Moon from Earth? (kilometres)",
                min_value=0.0,
                value=None,
                placeholder="Enter your estimate",
                step=1000.0,
                format="%.0f",
            )
            piano = st.number_input(
                "3. How many keys does a regular piano have?",
                min_value=0,
                value=None,
                placeholder="Enter your estimate",
                step=1,
                format="%d",
            )

            submitted = st.form_submit_button(
                "Submit my guesses",
                use_container_width=True,
            )

        if submitted:
            if tower is None or moon is None or piano is None:
                st.warning("Please enter an estimate for all three questions.")
            else:
                try:
                    with db() as conn:
                        conn.execute(
                            """
                            INSERT INTO submissions
                            (token_hash, tower, moon, piano, submitted_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                token_hash,
                                float(tower),
                                float(moon),
                                float(piano),
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )
                    st.success("Your guesses have been submitted. Thank you!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.info(
                        "A submission has already been recorded from this browser."
                    )

elif page == "Live results":
    st.subheader("Crowd results")
    st.caption(
        "Group statistics only. Individual guesses and individual rankings are not shown."
    )
    data = get_data()

    if data.empty:
        st.info("No guesses have been submitted yet.")
    else:
        st.metric("Total submissions", len(data))
        revealed = setting("revealed", "0") == "1"

        for key, question in QUESTIONS.items():
            st.markdown(f"### {question['title']}")
            mean_value = float(data[key].mean())
            median_value = float(data[key].median())

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Group mean", f"{mean_value:,.1f}")
            with col2:
                st.metric("Group median", f"{median_value:,.1f}")

            if revealed:
                actual = question["actual"]
                difference = mean_value - actual
                absolute_difference = abs(difference)
                if difference > 0:
                    comparison = f"{absolute_difference:,.1f} above the actual answer"
                elif difference < 0:
                    comparison = f"{absolute_difference:,.1f} below the actual answer"
                else:
                    comparison = "Exactly on the actual answer"

                st.markdown(
                    f"""
                    <div class="answer-card">
                        <div>Correct answer: <strong>{question['actual_display']}</strong></div>
                        <div>Group mean difference: <strong>{comparison}</strong></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.caption("The correct answer will appear after the host reveals it.")

elif page == "Host controls":
    st.subheader("Host controls")
    st.write("Host access only. Participants do not need a password to submit guesses.")

    host_password = st.secrets.get("HOST_PASSWORD", os.getenv("HOST_PASSWORD", ""))

    if not host_password:
        st.error(
            "Host password is not configured. Add HOST_PASSWORD to Streamlit Secrets before using host controls."
        )
    elif not host_is_authenticated():
        with st.form("host_login"):
            entered_password = st.text_input("Host password", type="password")
            login_clicked = st.form_submit_button("Unlock host controls")

        if login_clicked:
            if secrets.compare_digest(entered_password, str(host_password)):
                st.session_state.host_authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")
    else:
        st.success("Host controls unlocked.")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Reveal correct answers", use_container_width=True):
                set_setting("revealed", "1")
                st.success("Correct answers are now visible on Live results.")

        with col2:
            if st.button("Hide correct answers", use_container_width=True):
                set_setting("revealed", "0")
                st.success("Correct answers are hidden again.")

        st.divider()
        st.subheader("Share the quiz")
        app_url = st.text_input(
            "Public app URL",
            value="https://can-you-beat-the-crowd-uqs3hth434rfecdxnk3etz.streamlit.app/",
        )
        if app_url.strip():
            st.image(qr_bytes(app_url.strip()), caption="Scan to open the quiz", width=220)
            st.download_button(
                "Download QR code",
                data=qr_bytes(app_url.strip()),
                file_name="can-you-beat-the-crowd-qr.png",
                mime="image/png",
                use_container_width=True,
            )

        if st.button("Lock host controls"):
            st.session_state.host_authenticated = False
            st.rerun()

st.caption("Can You Beat the Crowd? · Anonymous estimates · No individual winner displayed")
