"""
main.py — FastAPI backend for YouTube StockFeed
Security:
  - CORS locked to GitHub Pages origin only
  - Referer/Origin header check on sensitive routes
  - Rate limiting per IP via slowapi
      · /api/channels/.../videos          → 20/hour  (YouTube quota guard)
      · /api/videos/.../summary/generate  → 40/hour  (AI cost guard)
      · clear-all saved                   → 3/hour   (destructive action)
      · all other routes                  → 100/hour (general headroom)

Limits sized for: 1-2hr/day, 20-30 videos, 5-10 channel loads per session.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
from dotenv import load_dotenv

from database import (
    init_db,
    get_or_create_user,
    get_user_channels,
    add_user_channel,
    remove_user_channel,
    save_video,
    get_saved_videos,
    remove_saved_video,
    clear_all_saved,
    get_summary,
    save_summary,
    get_journal,
)
from youtube import fetch_channel_videos
from summariser import generate_summary

load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://youtube-stockfeed.github.io")
FRONTEND_CORS_URL = os.getenv("FRONTEND_CORS_URL", "https://youtube-stockfeed.github.io")

ALLOWED_ORIGINS = [
    FRONTEND_URL,
    FRONTEND_CORS_URL,
    "http://localhost:3000",
    "http://127.0.0.1:5500",
    "null",
]

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["100/hour"])


# ── Startup ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="YouTube StockFeed API", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ── Origin guard ──────────────────────────────────────────────────────────────
def check_origin(request: Request):
    """Reject requests not from the authorised frontend. Skip in local dev."""
    origin  = request.headers.get("origin",  "")
    referer = request.headers.get("referer", "")
    local   = ["localhost", "127.0.0.1", "null", ""]
    if any(h in origin for h in local) or any(h in referer for h in local):
        return
    if FRONTEND_URL not in origin and FRONTEND_URL not in referer:
        raise HTTPException(status_code=403, detail="Forbidden: unauthorised origin.")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "app": "youtube-stockfeed"}


# ══════════════════════════════════════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════════════════════════════════════

class UserBody(BaseModel):
    user_id: str


@app.post("/api/users")
@limiter.limit("100/hour")
async def create_or_get_user(request: Request, body: UserBody):
    check_origin(request)
    if not body.user_id or len(body.user_id.strip()) < 2:
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters.")
    user_id = body.user_id.strip().lower()
    if not user_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Username may only contain letters, numbers, hyphens and underscores.")
    return get_or_create_user(user_id)


# ══════════════════════════════════════════════════════════════════════════════
# CHANNELS
# ══════════════════════════════════════════════════════════════════════════════

class ChannelBody(BaseModel):
    channel_id: str
    name: str
    short_name: str
    color: str = "#1a5fa8"


@app.get("/api/users/{user_id}/channels")
@limiter.limit("100/hour")
async def list_channels(request: Request, user_id: str):
    check_origin(request)
    return get_user_channels(user_id)


@app.post("/api/users/{user_id}/channels")
@limiter.limit("50/hour")
async def add_channel(request: Request, user_id: str, body: ChannelBody):
    check_origin(request)
    if not body.channel_id.startswith("UC") or len(body.channel_id) < 10:
        raise HTTPException(status_code=400, detail="Invalid YouTube channel ID (must start with UC).")
    return add_user_channel(user_id, body.channel_id, body.name, body.short_name, body.color)


@app.delete("/api/users/{user_id}/channels/{channel_id}")
@limiter.limit("50/hour")
async def delete_channel(request: Request, user_id: str, channel_id: str):
    check_origin(request)
    return remove_user_channel(user_id, channel_id)


# ══════════════════════════════════════════════════════════════════════════════
# VIDEOS
# 20/hour → protects YouTube 10,000 unit/day quota
# 10 channel loads × 100 units = 1,000 units per session — well within limit
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/channels/{channel_id}/videos")
@limiter.limit("20/hour")
async def get_videos(request: Request, channel_id: str):
    check_origin(request)
    if not channel_id.startswith("UC") or len(channel_id) < 10:
        raise HTTPException(status_code=400, detail="Invalid channel ID.")
    try:
        videos = await fetch_channel_videos(channel_id)
        return {"videos": videos, "count": len(videos)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YouTube API error: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARIES
# 40/hour → covers 30 videos/session comfortably over 2hrs
# Most will be cached after first view — actual Claude calls much lower
# ══════════════════════════════════════════════════════════════════════════════

class SummaryRequest(BaseModel):
    user_id: str
    title: str
    description: str


@app.get("/api/videos/{video_id}/summary")
@limiter.limit("100/hour")
async def get_video_summary(request: Request, video_id: str, user_id: str):
    check_origin(request)
    cached = get_summary(user_id, video_id)
    if cached:
        return cached
    raise HTTPException(status_code=404, detail="No saved summary found.")


@app.post("/api/videos/{video_id}/summary/generate")
@limiter.limit("40/hour")
async def generate_video_summary(request: Request, video_id: str, body: SummaryRequest):
    check_origin(request)
    if not body.title or len(body.title.strip()) < 3:
        raise HTTPException(status_code=400, detail="Video title too short.")
    try:
        result = await generate_summary(body.title, body.description)
        result["from_cache"] = False
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# SAVE / SAVED VIDEOS
# ══════════════════════════════════════════════════════════════════════════════

class SaveRequest(BaseModel):
    user_id: str
    video: dict
    summary: dict


@app.post("/api/saved")
@limiter.limit("50/hour")
async def save_analysis(request: Request, body: SaveRequest):
    check_origin(request)
    save_video(body.user_id, body.video)
    s = body.summary
    save_summary(
        body.user_id,
        body.video["video_id"],
        s.get("sentiment", "neutral"),
        s.get("digest", ""),
        s,
    )
    return {"ok": True, "message": "Analysis saved."}


@app.get("/api/users/{user_id}/saved")
@limiter.limit("100/hour")
async def list_saved(request: Request, user_id: str):
    check_origin(request)
    return {"saved": get_saved_videos(user_id)}


@app.delete("/api/users/{user_id}/saved/{video_id}")
@limiter.limit("50/hour")
async def delete_saved(request: Request, user_id: str, video_id: str):
    check_origin(request)
    return remove_saved_video(user_id, video_id)


@app.delete("/api/users/{user_id}/saved")
@limiter.limit("3/hour")
async def delete_all_saved(request: Request, user_id: str):
    check_origin(request)
    return clear_all_saved(user_id)


# ══════════════════════════════════════════════════════════════════════════════
# JOURNAL
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/users/{user_id}/journal")
@limiter.limit("100/hour")
async def get_user_journal(request: Request, user_id: str):
    check_origin(request)
    entries = get_journal(user_id)

    grouped = {}
    for entry in entries:
        date_key = entry["saved_at"][:10] if entry["saved_at"] else "Unknown"
        if date_key not in grouped:
            grouped[date_key] = []
        grouped[date_key].append(entry)

    result = [
        {"date": date, "entries": items}
        for date, items in sorted(grouped.items(), reverse=True)
    ]

    return {"journal": result, "total": len(entries)}
