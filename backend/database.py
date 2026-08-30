"""
database.py — Turso HTTP API (no special library needed)
Uses httpx directly to call Turso's REST API.
Works on any Python version. Zero compilation required.
"""

import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

TURSO_URL   = os.getenv("TURSO_DATABASE_URL", "")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

# Convert libsql:// to https:// for HTTP API
def get_http_url():
    url = TURSO_URL.replace("libsql://", "https://")
    return f"{url}/v2/pipeline"

def get_headers():
    return {
        "Authorization": f"Bearer {TURSO_TOKEN}",
        "Content-Type": "application/json",
    }


def execute(sql: str, params: list = []) -> list:
    """Execute a single SQL statement and return rows."""
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": [{"type": "text", "value": str(p)} if p is not None else {"type": "null"} for p in params]
                }
            },
            {"type": "close"}
        ]
    }
    resp = httpx.post(get_http_url(), headers=get_headers(), json=payload, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()
    result = data["results"][0]
    if result["type"] == "error":
        raise Exception(result["error"]["message"])
    rows = result.get("response", {}).get("result", {}).get("rows", [])
    return [[col["value"] for col in row] for row in rows]


def execute_many(statements: list) -> None:
    """Execute multiple SQL statements in one request."""
    requests = [
        {"type": "execute", "stmt": {"sql": sql, "args": [
            {"type": "text", "value": str(p)} if p is not None else {"type": "null"}
            for p in (params or [])
        ]}}
        for sql, params in statements
    ]
    requests.append({"type": "close"})
    payload = {"requests": requests}
    resp = httpx.post(get_http_url(), headers=get_headers(), json=payload, timeout=10.0)
    resp.raise_for_status()


def init_db():
    """Create all tables if they don't exist. Called on app startup."""
    statements = [
        ("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, created_at TEXT DEFAULT (datetime('now')))", []),
        ("""CREATE TABLE IF NOT EXISTS user_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            name TEXT NOT NULL,
            short_name TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#1a5fa8',
            position INTEGER DEFAULT 0,
            added_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, channel_id)
        )""", []),
        ("""CREATE TABLE IF NOT EXISTS saved_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            channel_name TEXT NOT NULL,
            title TEXT NOT NULL,
            thumbnail_url TEXT,
            published_at TEXT,
            saved_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, video_id)
        )""", []),
        ("""CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            sentiment TEXT,
            digest TEXT,
            summary_json TEXT,
            generated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, video_id)
        )""", []),
    ]
    execute_many(statements)


DEFAULT_CHANNELS = [
    {"channel_id": "UCwKB_00dPL3x5XmHF9IJCrg", "name": "Parkev Tatevosian CFA",   "short_name": "Parkev CFA",      "color": "#c2410c", "position": 0},
    {"channel_id": "UCtFqxbHLz0adgFLxRo9nLaA", "name": "3-Minute Breakdowns",       "short_name": "3-Min Breakdowns","color": "#b91c1c", "position": 1},
    {"channel_id": "UCyqlbzLoYtpqDXwRI9Yh5LA", "name": "BWB Business With Brian",   "short_name": "BWB Brian",       "color": "#047857", "position": 2},
]


# ── Users ─────────────────────────────────────────────────────────────────────
def get_or_create_user(user_id: str) -> dict:
    rows = execute("SELECT id, created_at FROM users WHERE id = ?", [user_id])
    if rows:
        return {"id": rows[0][0], "created_at": rows[0][1], "is_new": False}

    execute_many([
        ("INSERT OR IGNORE INTO users (id) VALUES (?)", [user_id]),
        *[
            ("INSERT OR IGNORE INTO user_channels (user_id, channel_id, name, short_name, color, position) VALUES (?, ?, ?, ?, ?, ?)",
             [user_id, ch["channel_id"], ch["name"], ch["short_name"], ch["color"], ch["position"]])
            for ch in DEFAULT_CHANNELS
        ]
    ])
    rows = execute("SELECT id, created_at FROM users WHERE id = ?", [user_id])
    return {"id": rows[0][0], "created_at": rows[0][1], "is_new": True}


# ── Channels ──────────────────────────────────────────────────────────────────
def get_user_channels(user_id: str) -> list:
    rows = execute(
        "SELECT channel_id, name, short_name, color, position FROM user_channels WHERE user_id = ? ORDER BY position ASC",
        [user_id]
    )
    return [{"channel_id": r[0], "name": r[1], "short_name": r[2], "color": r[3], "position": r[4]} for r in rows]


def add_user_channel(user_id: str, channel_id: str, name: str, short_name: str, color: str) -> dict:
    rows = execute("SELECT COALESCE(MAX(position), -1) FROM user_channels WHERE user_id = ?", [user_id])
    max_pos = int(rows[0][0]) if rows else -1
    execute("INSERT OR IGNORE INTO user_channels (user_id, channel_id, name, short_name, color, position) VALUES (?, ?, ?, ?, ?, ?)",
            [user_id, channel_id, name, short_name, color, max_pos + 1])
    return {"ok": True}


def remove_user_channel(user_id: str, channel_id: str) -> dict:
    execute("DELETE FROM user_channels WHERE user_id = ? AND channel_id = ?", [user_id, channel_id])
    return {"ok": True}


# ── Saved videos ──────────────────────────────────────────────────────────────
def save_video(user_id: str, video: dict) -> dict:
    execute(
        "INSERT OR IGNORE INTO saved_videos (video_id, user_id, channel_id, channel_name, title, thumbnail_url, published_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [video["video_id"], user_id, video["channel_id"], video["channel_name"],
         video["title"], video.get("thumbnail_url", ""), video.get("published_at", "")]
    )
    return {"ok": True}


def get_saved_videos(user_id: str) -> list:
    rows = execute(
        "SELECT video_id, channel_id, channel_name, title, thumbnail_url, published_at, saved_at FROM saved_videos WHERE user_id = ? ORDER BY saved_at DESC",
        [user_id]
    )
    return [{"video_id": r[0], "channel_id": r[1], "channel_name": r[2], "title": r[3],
             "thumbnail_url": r[4], "published_at": r[5], "saved_at": r[6]} for r in rows]


def remove_saved_video(user_id: str, video_id: str) -> dict:
    execute_many([
        ("DELETE FROM saved_videos WHERE user_id = ? AND video_id = ?", [user_id, video_id]),
        ("DELETE FROM summaries WHERE user_id = ? AND video_id = ?",    [user_id, video_id]),
    ])
    return {"ok": True}


def clear_all_saved(user_id: str) -> dict:
    execute_many([
        ("DELETE FROM saved_videos WHERE user_id = ?", [user_id]),
        ("DELETE FROM summaries WHERE user_id = ?",    [user_id]),
    ])
    return {"ok": True}


# ── Summaries ─────────────────────────────────────────────────────────────────
def get_summary(user_id: str, video_id: str):
    rows = execute(
        "SELECT sentiment, digest, summary_json, generated_at FROM summaries WHERE user_id = ? AND video_id = ?",
        [user_id, video_id]
    )
    if not rows:
        return None
    r = rows[0]
    return {"sentiment": r[0], "digest": r[1],
            "summary_json": json.loads(r[2]) if r[2] else {},
            "generated_at": r[3], "from_cache": True}


def save_summary(user_id: str, video_id: str, sentiment: str, digest: str, summary_json: dict) -> dict:
    execute(
        "INSERT OR REPLACE INTO summaries (video_id, user_id, sentiment, digest, summary_json) VALUES (?, ?, ?, ?, ?)",
        [video_id, user_id, sentiment, digest, json.dumps(summary_json)]
    )
    return {"ok": True}


# ── Journal ───────────────────────────────────────────────────────────────────
def get_journal(user_id: str) -> list:
    rows = execute(
        """SELECT sv.video_id, sv.title, sv.channel_name, sv.thumbnail_url,
                  sv.published_at, sv.saved_at, s.sentiment, s.digest
           FROM saved_videos sv
           LEFT JOIN summaries s ON s.video_id = sv.video_id AND s.user_id = sv.user_id
           WHERE sv.user_id = ?
           ORDER BY sv.saved_at DESC""",
        [user_id]
    )
    return [{"video_id": r[0], "title": r[1], "channel_name": r[2], "thumbnail_url": r[3],
             "published_at": r[4], "saved_at": r[5], "sentiment": r[6], "digest": r[7]} for r in rows]
