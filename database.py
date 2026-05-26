"""SQLite-схема под forecast_prophet / routing / pdf_report + лог уведомлений."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
import pandas as pd

DB_PATH = Path(__file__).parent / "data.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS containers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                address TEXT,
                lat REAL,
                lon REAL,
                capacity_liters INTEGER DEFAULT 1100
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fill_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                container_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                fill_percent REAL NOT NULL,
                FOREIGN KEY (container_id) REFERENCES containers(id)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fh_cid ON fill_history(container_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fh_ts  ON fill_history(timestamp)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT DEFAULT CURRENT_TIMESTAMP,
                level TEXT,
                message TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                channel     TEXT    NOT NULL,
                recipient   TEXT,
                subject     TEXT,
                message     TEXT    NOT NULL,
                status      TEXT    NOT NULL,
                error       TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notif_ts ON notifications(ts)")


def log_event(level: str, message: str):
    with get_conn() as conn:
        conn.execute("INSERT INTO events (level, message) VALUES (?, ?)", (level, message))


def get_history(container_id, hours=168, **kwargs):
    with get_conn() as conn:
        df = pd.read_sql_query(
            """SELECT timestamp, fill_percent
               FROM fill_history
               WHERE container_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            conn, params=(int(container_id), int(hours))
        )
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def get_containers():
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM containers", conn)


def get_latest_fills():
    with get_conn() as conn:
        return pd.read_sql_query("""
            SELECT c.id, c.name, c.address, c.lat, c.lon, c.capacity_liters,
                   (SELECT fill_percent FROM fill_history
                    WHERE container_id = c.id
                    ORDER BY timestamp DESC LIMIT 1) AS current_fill,
                   (SELECT timestamp FROM fill_history
                    WHERE container_id = c.id
                    ORDER BY timestamp DESC LIMIT 1) AS last_ts
            FROM containers c
        """, conn)


def log_notification(channel, message, status="ok",
                     recipient=None, subject=None, error=None):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO notifications (channel, recipient, subject, message, status, error)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (channel, recipient, subject, message, status, error))


def get_notifications(limit=100):
    with get_conn() as conn:
        return pd.read_sql_query("""
            SELECT id, ts, channel, status, recipient, subject, message, error
            FROM notifications
            ORDER BY id DESC
            LIMIT ?
        """, conn, params=(int(limit),))


def clear_notifications():
    with get_conn() as conn:
        conn.execute("DELETE FROM notifications")
