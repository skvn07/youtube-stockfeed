"""
summariser.py — Claude API summarisation
Auto-detects stock vs macro videos and returns structured JSON + digest.
"""

import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


async def generate_summary(title: str, description: str) -> dict:
    """
    Generate a structured AI summary for a video.
    Auto-detects type: 'stock' or 'macro'.
    Returns: { type, sentiment, digest, takeaways, stocks (if stock type), themes (if macro) }
    """

    prompt = f"""You are an expert finance analyst summarising YouTube videos for busy investors.

Analyse this video and respond ONLY with a valid JSON object — no markdown, no backticks, no preamble.

Video title: "{title}"
Video description: "{description[:1200]}"

Determine the video type:
- "stock" → focuses on specific companies/tickers/earnings
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

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        data = resp.json()

    raw_text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            raw_text += block.get("text", "")

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
        # Fallback if Claude returns something unexpected
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
