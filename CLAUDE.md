# CLAUDE.md — SF Trending Eats

## Project
Social-media-powered trending restaurants product for the SF Bay Area. Surfaces restaurants that are trending on TikTok, Instagram, Reddit, and Threads before traditional food media covers them. Newsletter-first distribution via Beehiiv, web dashboard on Vercel.

## Build & Dev Commands
- **Pipeline (collect):** `cd pipeline && python run_collection.py`
- **Pipeline (publish):** `cd pipeline && python run_weekly_publish.py`
- **Web dev:** `cd web && npm run dev`
- **Web build:** `cd web && npm run build`
- **Install Python deps:** `pip install -r requirements.txt`
- **Install web deps:** `cd web && npm install`
- **DB setup:** `psql -f db/schema.sql`

## Architecture
```
pipeline/
  collectors/       — Data collectors per platform (Yelp, Reddit, TikTok, Instagram, Threads, Google)
  scoring/          — Trend scoring engine (5-signal algorithm)
  utils/            — DB, NLP, restaurant matching utilities
  publisher.py      — Newsletter and social media publishing
  run_collection.py — Main collection runner
  run_weekly_publish.py — Weekly publish runner
config/
  settings.py       — API keys, scoring weights, hashtag lists
web/
  app/              — Next.js pages
  components/       — React components (TrendingList, NewsletterSignup)
  lib/data/         — trending.json (pipeline output)
db/
  schema.sql        — TimescaleDB schema (hypertables, aggregates)
```

## Scoring Algorithm
5 signals with z-score normalization:
- Mention velocity (30%) — rate of new mentions vs 30-day baseline
- Engagement acceleration (25%) — rate of change in likes/comments
- Cross-platform spread (20%) — trending on multiple platforms simultaneously
- Sentiment score (15%) — NLP positive/negative analysis
- Influencer signal (10%) — high-reach account mentions

## Data Sources
- **TikTok:** Apify scraper (~$5-15/mo) — hashtag search
- **Instagram:** Graph API (30 hashtags/week limit) + Apify fallback
- **Reddit:** r/SFFood, r/sanfrancisco, r/bayarea
- **Threads:** Meta Threads API (keyword search)
- **Yelp:** Fusion API hot_and_new filter
- **Google Places:** Review velocity tracking

## Skills
- **restaurant-finder** — Dining concierge skill that recommends restaurants based on social media virality and food media buzz. Located at `.claude/skills/restaurant-finder.md`

## Rules
- NEVER store individual user identities — aggregate and anonymize all social data
- API keys go in .env (never committed) — see .env.example
- Scoring weights are configured in config/settings.py, not hardcoded in engine
- All collectors must handle rate limits gracefully with exponential backoff
- Restaurant name matching must validate against Yelp/Google Places before storing
