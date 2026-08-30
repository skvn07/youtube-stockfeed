"""
youtube.py — YouTube Data API v3 fetching
Fetches latest videos for a channel, always live (no server-side cache).
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

YT_API_KEY = os.getenv("YOUTUBE_API_KEY")
YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


async def fetch_channel_videos(channel_id: str, max_pages: int = 4) -> list:
    """
    Fetch latest videos from a YouTube channel.
    Returns up to max_pages * 50 videos, ordered latest first.
    max_pages=4 gives up to 200 videos — plenty for a live feed.
    """
    videos = []
    page_token = ""

    async with httpx.AsyncClient(timeout=15.0) as client:
        for _ in range(max_pages):
            params = {
                "key": YT_API_KEY,
                "channelId": channel_id,
                "part": "snippet",
                "type": "video",
                "order": "date",
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.get(YT_SEARCH_URL, params=params)
            data = resp.json()

            if "error" in data:
                raise ValueError(data["error"].get("message", "YouTube API error"))

            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                thumbs = snippet.get("thumbnails", {})
                thumb_url = (
                    thumbs.get("medium", {}).get("url")
                    or thumbs.get("default", {}).get("url")
                    or ""
                )
                videos.append({
                    "video_id": item["id"]["videoId"],
                    "channel_id": channel_id,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "thumbnail_url": thumb_url,
                    "published_at": snippet.get("publishedAt", ""),
                    "channel_name": snippet.get("channelTitle", ""),
                })

            page_token = data.get("nextPageToken", "")
            if not page_token:
                break

    # Sort latest first (API usually returns in order, but let's be safe)
    videos.sort(key=lambda v: v["published_at"], reverse=True)
    return videos
