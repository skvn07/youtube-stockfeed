"""
database.py — Turso (libSQL) database setup and all DB functions
Connects to Turso cloud SQLite for persistent free storage.
"""

import os
import json
import libsql_experimental as libsql
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN")


def get_conn():
    """Get a Turso database connection."""
    return libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)


def init_db():
    """Create all tables if they don't exist. Called on app startup."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id),
            channel_id TEXT NOT NULL,
            name TEXT NOT NULL,
            short_name TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#1a5fa8',
            position INTEGER DEFAULT 0,
            added_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, channel_id)
        );

        CREATE TABLE IF NOT EXISTS saved_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            user_id TEXT NOT NULL REFERENCES users(id),
            channel_id TEXT NOT NULL,
            channel_name TEXT NOT NULL,
            title TEXT NOT NULL,
            thumbnail_url TEXT,
            published_at TEXT,
            saved_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, video_id)
        );

        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            user_id TEXT NOT NULL REFERENCES users(id),
            sentiment TEXT,
            digest TEXT,
            summary_json TEXT,
            generated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, video_id)
        );
    """)
    conn.commit()
    conn.close()


# ── Default channels seeded for every new user ──────────────────────────────
DEFAULT_CHANNELS = [
    {
        "channel_id": "UCwKB_00dPL3x5XmHF9IJCrg",
        "name": "Parkev Tatevosian CFA",
        "short_name": "Parkev CFA",
        "color": "#c2410c",
        "position": 0,
    },
    {
        "channel_id": "UCtFqxbHLz0adgFLxRo9nLaA",
        "name": "3-Minute Breakdowns",
        "short_name": "3-Min Breakdowns",
        "color": "#b91c1c",
        "position": 1,
    },
    {
        "channel_id": "UCyqlbzLoYtpqDXwRI9Yh5LA",
        "name": "BWB Business With Brian",
        "short_name": "BWB Brian",
        "color": "#047857",
        "position": 2,
    },
]


# ── Users ────────────────────────────────────────────────────────────────────
def get_or_create_user(user_id: str) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT id, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    if row:
        conn.close()
        return {"id": row[0], "created_at": row[1], "is_new": False}

    # New user — create and seed default channels
    conn.execute("INSERT INTO users (id) VALUES (?)", (user_id,))
    for ch in DEFAULT_CHANNELS:
        conn.execute(
            """INSERT OR IGNORE INTO user_channels
               (user_id, channel_id, name, short_name, color, position)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, ch["channel_id"], ch["name"], ch["short_name"], ch["color"], ch["position"]),
        )
    conn.commit()
    row = conn.execute("SELECT id, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return {"id": row[0], "created_at": row[1], "is_new": True}


# ── Channels ─────────────────────────────────────────────────────────────────
def get_user_channels(user_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT channel_id, name, short_name, color, position
           FROM user_channels WHERE user_id = ?
           ORDER BY position ASC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [
        {"channel_id": r[0], "name": r[1], "short_name": r[2], "color": r[3], "position": r[4]}
        for r in rows
    ]


def add_user_channel(user_id: str, channel_id: str, name: str, short_name: str, color: str) -> dict:
    conn = get_conn()
    max_pos = conn.execute(
        "SELECT COALESCE(MAX(position), -1) FROM user_channels WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    conn.execute(
        """INSERT OR IGNORE INTO user_channels
           (user_id, channel_id, name, short_name, color, position)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, channel_id, name, short_name, color, max_pos + 1),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def remove_user_channel(user_id: str, channel_id: str) -> dict:
    conn = get_conn()
    conn.execute(
        "DELETE FROM user_channels WHERE user_id = ? AND channel_id = ?",
        (user_id, channel_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


# ── Saved videos ─────────────────────────────────────────────────────────────
def save_video(user_id: str, video: dict) -> dict:
    conn = get_conn()
    conn.execute(
        """INSERT OR IGNORE INTO saved_videos
           (video_id, user_id, channel_id, channel_name, title, thumbnail_url, published_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            video["video_id"],
            user_id,
            video["channel_id"],
            video["channel_name"],
            video["title"],
            video.get("thumbnail_url", ""),
            video.get("published_at", ""),
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def get_saved_videos(user_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        """SELECT video_id, channel_id, channel_name, title, thumbnail_url, published_at, saved_at
           FROM saved_videos WHERE user_id = ?
           ORDER BY saved_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "video_id": r[0],
            "channel_id": r[1],
            "channel_name": r[2],
            "title": r[3],
            "thumbnail_url": r[4],
            "published_at": r[5],
            "saved_at": r[6],
        }
        for r in rows
    ]


def remove_saved_video(user_id: str, video_id: str) -> dict:
    conn = get_conn()
    conn.execute(
        "DELETE FROM saved_videos WHERE user_id = ? AND video_id = ?",
        (user_id, video_id),
    )
    conn.execute(
        "DELETE FROM summaries WHERE user_id = ? AND video_id = ?",
        (user_id, video_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def clear_all_saved(user_id: str) -> dict:
    conn = get_conn()
    conn.execute("DELETE FROM saved_videos WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM summaries WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ── Summaries ─────────────────────────────────────────────────────────────────
def get_summary(user_id: str, video_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        """SELECT sentiment, digest, summary_json, generated_at
           FROM summaries WHERE user_id = ? AND video_id = ?""",
        (user_id, video_id),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "sentiment": row[0],
        "digest": row[1],
        "summary_json": json.loads(row[2]) if row[2] else {},
        "generated_at": row[3],
        "from_cache": True,
    }


def save_summary(user_id: str, video_id: str, sentiment: str, digest: str, summary_json: dict) -> dict:
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO summaries
           (video_id, user_id, sentiment, digest, summary_json)
           VALUES (?, ?, ?, ?, ?)""",
        (video_id, user_id, sentiment, digest, json.dumps(summary_json)),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


# ── Journal (summary history) ─────────────────────────────────────────────────
def get_journal(user_id: str) -> list:
    """Return all saved summaries with video info, grouped by date, latest first."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT
               sv.video_id, sv.title, sv.channel_name, sv.thumbnail_url,
               sv.published_at, sv.saved_at,
               s.sentiment, s.digest
           FROM saved_videos sv
           LEFT JOIN summaries s ON s.video_id = sv.video_id AND s.user_id = sv.user_id
           WHERE sv.user_id = ?
           ORDER BY sv.saved_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "video_id": r[0],
            "title": r[1],
            "channel_name": r[2],
            "thumbnail_url": r[3],
            "published_at": r[4],
            "saved_at": r[5],
            "sentiment": r[6],
            "digest": r[7],
        }
        for r in rows
    ]
