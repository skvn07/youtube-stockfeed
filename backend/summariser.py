"""
summariser.py — Google Gemini 2.5 Flash summarisation (free tier)
Auto-detects stock vs macro videos and returns structured JSON + digest.
"""

import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


async def generate_summary(title: str, description: str) -> dict:
    """
    Generate a structured AI summary for a video using Gemini 2.5 Flash.
    Auto-detects type: 'stock' or 'macro'.
    Returns: { type, sentiment, digest, takeaways, stocks (stock) or themes (macro) }
    """

    prompt = f"""You are an expert finance analyst summarising YouTube videos for busy investors.

Analyse this video and respond ONLY with a valid JSON object — no markdown, no backticks, no preamble.

Video title: "{title}"
Video description: "{description[:1200]}"

Determine the video type:
- "stock" → focuses on specific companies, tickers, earnings, or valuations
- "macro" → focuses on economy, interest rates, inflation, global events, general investing

Return this exact JSON structure:

For STOCK type:
{{
  "type": "stock",
  "sentiment": "bullish" | "cautious" | "bearish" | "neutral",
  "digest": "2-3 sentence plain summary for the journal view. Be specific with numbers and tickers.",
  "takeaways": {{
    "focus": "What company/ticker and specific event or report discussed",
    "argument": "The host's core investment argument",
    "valuation": "Any price targets, P/E ratios, or valuations mentioned",
    "recommendation": "The host's final recommendation for investors"
  }},
  "stocks": [
    {{"ticker": "TICKER", "action": "Buy|Hold|Sell|Watch", "entry": "$xxx or null", "stop_loss": "$xxx or null"}}
  ]
}}

For MACRO type:
{{
  "type": "macro",
  "sentiment": "bullish" | "cautious" | "bearish" | "neutral",
  "digest": "2-3 sentence plain summary for the journal view. Include key data points.",
  "takeaways": {{
    "topic": "The main economic topic or event covered",
    "argument": "The host's core argument or view",
    "data": "Key statistics, figures, or data mentioned",
    "impact": "How this affects markets or portfolios",
    "action": "What the host recommends investors do"
  }},
  "themes": ["theme1", "theme2", "theme3"]
}}

Respond with ONLY the JSON. No other text."""

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1000,
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json=payload,
        )
        data = resp.json()

    # Extract text from Gemini response structure
    try:
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raw_text = ""

    # Strip any accidental markdown fences
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    raw_text = raw_text.strip().rstrip("```").strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        # Fallback if response is unexpected
        result = {
            "type": "macro",
            "sentiment": "neutral",
            "digest": f"{title} — summary could not be parsed.",
            "takeaways": {
                "topic": title,
                "argument": "See video for details.",
                "data": "—",
                "impact": "—",
                "action": "—",
            },
            "themes": ["Finance"],
        }

    return result
