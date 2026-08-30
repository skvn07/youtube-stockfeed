# YouTube StockFeed 📈

AI-powered YouTube finance video digest. Browse channels, get Claude-generated summaries, save analyses to your personal journal.

**Live URL:** https://youtube-stockfeed.github.io  
**Stack:** GitHub Pages + Render (FastAPI) + Turso (SQLite) — **£0/month**

---

## Project Structure

```
youtube-stockfeed/
├── backend/
│   ├── main.py           ← FastAPI routes
│   ├── database.py       ← Turso/SQLite functions
│   ├── youtube.py        ← YouTube API fetching
│   ├── summariser.py     ← Claude AI summaries
│   ├── requirements.txt
│   └── .env.example      ← copy to .env and fill in keys
├── frontend/
│   └── index.html        ← complete single-file UI
├── .gitignore
└── README.md
```

---

## Step 1 — Set up Turso (database)

1. Go to [turso.tech](https://turso.tech) and sign in
2. Install the Turso CLI:
   ```bash
   curl -sSfL https://get.tur.so/install.sh | bash
   ```
3. Restart your terminal, then login:
   ```bash
   turso auth login
   ```
4. Create your database:
   ```bash
   turso db create youtube-stockfeed
   ```
5. Get your database URL:
   ```bash
   turso db show youtube-stockfeed --url
   # → libsql://youtube-stockfeed-skvn07.turso.io
   ```
6. Create an auth token:
   ```bash
   turso db tokens create youtube-stockfeed
   # → eyJh... (long token string)
   ```
7. Save both — you'll need them in Step 3.

---

## Step 2 — Push code to GitHub

1. Create a new repo named exactly: `youtube-stockfeed.github.io`
   - Go to github.com → New repository
   - Name: `youtube-stockfeed.github.io`
   - Set to **Public**
   - Do NOT initialise with README

2. Push this project:
   ```bash
   cd youtube-stockfeed
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/skvn07/youtube-stockfeed.github.io.git
   git push -u origin main
   ```

3. Enable GitHub Pages:
   - Go to repo → Settings → Pages
   - Source: Deploy from branch → `main` → `/frontend` folder
   - Save → your frontend is live at `https://youtube-stockfeed.github.io`

---

## Step 3 — Deploy backend on Render

1. Go to [render.com](https://render.com) and sign in with GitHub

2. Click **New → Web Service**

3. Connect your `youtube-stockfeed.github.io` repo

4. Configure the service:
   - **Name:** `youtube-stockfeed-api`
   - **Root directory:** `backend`
   - **Environment:** `Python 3`
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn main:app --host 0.0.0.0 --port 10000`
   - **Plan:** `Free`

5. Add Environment Variables:

   | Key | Value |
   |-----|-------|
   | `YOUTUBE_API_KEY` | your YouTube Data API v3 key |
   | `GEMINI_API_KEY` | your Gemini API key from aistudio.google.com |
   | `TURSO_DATABASE_URL` | `libsql://youtube-stockfeed-skvn07.turso.io` |
   | `TURSO_AUTH_TOKEN` | your Turso token |
   | `FRONTEND_URL` | `https://youtube-stockfeed.github.io` |

6. Click **Deploy Web Service**

7. Wait ~3 minutes. Your backend URL will be:
   `https://youtube-stockfeed-api.onrender.com`

---

## Step 4 — Connect frontend to backend

1. Open `frontend/index.html`
2. Find this line near the top of the `<script>` section:
   ```js
   const BACKEND_URL = 'https://youtube-stockfeed-api.onrender.com';
   ```
3. Confirm it matches your actual Render URL exactly
4. Push the update:
   ```bash
   git add frontend/index.html
   git commit -m "Set backend URL"
   git push
   ```

GitHub Pages deploys automatically in ~1 minute.

---

## Step 5 — Test it

1. Open `https://youtube-stockfeed.github.io`
2. Enter a username → Continue
3. 3 default channels are pre-loaded
4. Click a channel → videos load from YouTube
5. Click a video → Claude generates a summary
6. Click "Save this analysis" → saved to Turso DB
7. Click 📋 Summary to see your journal

---

## Sharing with friends

Just send them: `https://youtube-stockfeed.github.io`

Each person enters their own username and gets their own private feed, channel list, and saved analyses — completely separate from everyone else.

---

## Getting your YouTube API key

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project (e.g. `youtube-stockfeed`)
3. APIs & Services → Library → search **YouTube Data API v3** → Enable
4. APIs & Services → Credentials → Create Credentials → API Key
5. Copy the key (starts with `AIza...`)

**Free quota:** 10,000 units/day. Each channel load ≈ 100 units.

---

## Getting your Anthropic API key

1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Sign in with your Google account
3. Click Get API key → Create API key
4. Copy the key (starts with `AIzaSy...`)

**Cost:** ~$0.001–0.003 per summary. Summaries are cached — each video paid for once only.

---

## Local development

```bash
cd backend
cp .env.example .env
# Fill in your keys in .env

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open `frontend/index.html` directly in your browser for local testing.

---

## Cost summary

| Item | Cost |
|------|------|
| GitHub Pages | Free |
| Render (Hobby plan) | Free |
| Turso (free tier) | Free |
| YouTube Data API | Free (10k units/day) |
| Anthropic API | ~$0.10 total for hundreds of summaries |
| **Total** | **£0/month** |
