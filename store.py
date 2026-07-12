"""SQLite persistence: per-user conversation sessions, leads and pickup requests.

A tiny, dependency-free store. The DB file is created automatically on first run.
Sessions hold the current conversation state + collected fields so the bot can
carry a multi-step conversation across messages.

Uses WAL journal mode with generous busy_timeout for thread safety.
Runs behind Gunicorn with --workers 1 --threads 4 so all threads share
one process and WAL handles concurrency without locking issues.
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager

# Override with the GPX_DB_PATH env var (e.g. a persistent disk path in prod).
DB_PATH = os.getenv("GPX_DB_PATH", "gpx_bot.db")


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    with _conn() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            " wa_id TEXT PRIMARY KEY,"
            " state TEXT NOT NULL DEFAULT 'MENU',"
            " data TEXT NOT NULL DEFAULT '{}',"
            " updated REAL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS leads ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " wa_id TEXT,"
            " kind TEXT,"
            " payload TEXT,"
            " created REAL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS learning_log ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " wa_id TEXT,"
            " channel TEXT,"
            " state TEXT,"
            " user_input TEXT,"
            " category TEXT DEFAULT 'unknown',"
            " resolved INTEGER DEFAULT 0,"
            " admin_mapping TEXT,"
            " created REAL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS smart_aliases ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " user_input TEXT UNIQUE,"
            " maps_to TEXT,"
            " added_by TEXT DEFAULT 'auto',"
            " created REAL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS follow_ups ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " channel TEXT,"
            " user_id TEXT,"
            " message TEXT,"
            " send_after REAL,"
            " sent INTEGER DEFAULT 0,"
            " created REAL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS media_log ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " wa_id TEXT,"
            " channel TEXT,"
            " media_type TEXT,"
            " media_id TEXT,"
            " caption TEXT,"
            " created REAL)"
        )


# ---- Session helpers ----------------------------------------------------
SESSION_TTL = 60 * 30  # 30 minutes of inactivity resets the conversation


def get_session(wa_id):
    with _conn() as con:
        row = con.execute("SELECT * FROM sessions WHERE wa_id=?", (wa_id,)).fetchone()
    if row is None:
        return {"wa_id": wa_id, "state": "MENU", "data": {}}
    if row["updated"] and (time.time() - row["updated"]) > SESSION_TTL:
        return {"wa_id": wa_id, "state": "MENU", "data": {}}
    return {"wa_id": wa_id, "state": row["state"], "data": json.loads(row["data"] or "{}")}


def save_session(wa_id, state, data):
    with _conn() as con:
        con.execute(
            "INSERT INTO sessions (wa_id, state, data, updated) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(wa_id) DO UPDATE SET state=excluded.state, "
            "data=excluded.data, updated=excluded.updated",
            (wa_id, state, json.dumps(data), time.time()),
        )


def reset_session(wa_id):
    save_session(wa_id, "MENU", {})


# ---- Lead helpers -------------------------------------------------------
def save_lead(wa_id, kind, payload):
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO leads (wa_id, kind, payload, created) VALUES (?, ?, ?, ?)",
            (wa_id, kind, json.dumps(payload), time.time()),
        )
        return cur.lastrowid


def recent_leads(limit=50):
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM leads ORDER BY created DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---- Auto-learning helpers ----------------------------------------------
def log_unrecognized(wa_id, channel, state, user_input, category="destination"):
    """Log an unrecognized user input for later review / alias creation."""
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO learning_log (wa_id, channel, state, user_input, category, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (wa_id, channel, state, user_input, category, time.time()),
        )
        return cur.lastrowid


def get_smart_alias(text):
    """Look up a smart alias (case-insensitive). Returns the maps_to value or None."""
    with _conn() as con:
        row = con.execute(
            "SELECT maps_to FROM smart_aliases WHERE LOWER(user_input) = LOWER(?)",
            (text,),
        ).fetchone()
    return row["maps_to"] if row else None


def add_smart_alias(user_input, maps_to, added_by="admin"):
    """Insert or replace a smart alias mapping."""
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO smart_aliases (user_input, maps_to, added_by, created) "
            "VALUES (?, ?, ?, ?)",
            (user_input, maps_to, added_by, time.time()),
        )


def get_unrecognized(limit=100):
    """Return recent unrecognized queries (resolved=0), grouped with occurrence counts."""
    with _conn() as con:
        rows = con.execute(
            "SELECT user_input, category, COUNT(*) AS cnt, "
            "MIN(id) AS first_id, MAX(created) AS last_seen "
            "FROM learning_log WHERE resolved = 0 "
            "GROUP BY LOWER(user_input), category "
            "ORDER BY cnt DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_resolved(learning_id):
    """Mark a single learning_log entry as resolved."""
    with _conn() as con:
        con.execute(
            "UPDATE learning_log SET resolved = 1 WHERE id = ?", (learning_id,)
        )


def get_learning_stats():
    """Return summary stats about the learning log."""
    with _conn() as con:
        total = con.execute(
            "SELECT COUNT(*) FROM learning_log"
        ).fetchone()[0]
        unique = con.execute(
            "SELECT COUNT(DISTINCT LOWER(user_input)) FROM learning_log WHERE resolved = 0"
        ).fetchone()[0]
        resolved = con.execute(
            "SELECT COUNT(*) FROM learning_log WHERE resolved = 1"
        ).fetchone()[0]
    return {
        "total_unrecognized": total,
        "unique_queries": unique,
        "resolved_count": resolved,
    }


def get_smart_aliases():
    """Return all smart aliases as a list of dicts."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, user_input, maps_to, added_by, created FROM smart_aliases "
            "ORDER BY created DESC"
        ).fetchall()
    return [{"id": r["id"], "input": r["user_input"], "maps_to": r["maps_to"],
             "added_by": r["added_by"]} for r in rows]


def delete_smart_alias(alias_id):
    """Delete a smart alias by id."""
    with _conn() as con:
        con.execute("DELETE FROM smart_aliases WHERE id = ?", (alias_id,))


def mark_resolved_by_input(input_text):
    """Mark all learning_log entries matching this input as resolved."""
    with _conn() as con:
        con.execute(
            "UPDATE learning_log SET resolved = 1 WHERE LOWER(user_input) = LOWER(?)",
            (input_text,),
        )


# ---- Follow-up scheduling -----------------------------------------------
def _ensure_followups_table():
    """Create the follow_ups table if it doesn't exist."""
    with _conn() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS follow_ups ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " channel TEXT,"
            " user_id TEXT,"
            " message TEXT,"
            " send_after REAL,"
            " sent INTEGER DEFAULT 0,"
            " created REAL)"
        )


def schedule_followup(channel, user_id, message, delay_seconds=3600):
    """Schedule a follow-up message to be sent after delay_seconds."""
    _ensure_followups_table()
    send_after = time.time() + delay_seconds
    with _conn() as con:
        con.execute(
            "INSERT INTO follow_ups (channel, user_id, message, send_after, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (channel, user_id, message, send_after, time.time()),
        )


def get_pending_followups():
    """Return follow-ups that are due and not yet sent."""
    _ensure_followups_table()
    now = time.time()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM follow_ups WHERE sent = 0 AND send_after <= ? "
            "ORDER BY send_after ASC LIMIT 50",
            (now,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_followup_sent(followup_id):
    """Mark a follow-up as sent."""
    with _conn() as con:
        con.execute(
            "UPDATE follow_ups SET sent = 1 WHERE id = ?", (followup_id,)
        )


# ---- Media log -----------------------------------------------------------
def _ensure_media_table():
    """Create the media_log table if it doesn't exist."""
    with _conn() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS media_log ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " wa_id TEXT,"
            " channel TEXT,"
            " media_type TEXT,"
            " media_id TEXT,"
            " caption TEXT,"
            " created REAL)"
        )


def log_media(wa_id, channel, media_type, media_id, caption=""):
    """Log a received media message (image, document, etc.)."""
    _ensure_media_table()
    with _conn() as con:
        con.execute(
            "INSERT INTO media_log (wa_id, channel, media_type, media_id, caption, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (wa_id, channel, media_type, media_id, caption, time.time()),
        )
