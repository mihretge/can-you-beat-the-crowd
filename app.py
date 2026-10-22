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
