# SF Trending Eats 🍜📈

**Discover Bay Area restaurants before they blow up.**

SF Trending Eats surfaces the top trending restaurants in the San Francisco Bay Area each week by monitoring social media signals, review velocity, and community buzz. Built for Gen Z and Millennials who discover food through TikTok, Instagram, and Reddit, not Google or Yelp.

## How It Works

A Python data pipeline collects signals from multiple sources every 6 hours, computes an **engagement velocity score** for each restaurant, and publishes a weekly ranked list through three channels:

1. **Web dashboard** (Next.js on Vercel) with interactive trending rankings
2. **Email newsletter** (Beehiiv) delivered every Tuesday morning
3. **Social media** (TikTok, Instagram, Threads) via OpenClaw + Genviral

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   DATA SOURCES                       │
│  Yelp API · Reddit API · Threads API · Google Places │
│  Google Trends                                       │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              PYTHON DATA PIPELINE                    │
│  Collectors → NLP Sentiment → Trend Scoring Engine   │
│  Runs every 6 hours via GitHub Actions               │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              POSTGRESQL + TIMESCALEDB                │
│  Mentions · Engagement Snapshots · Trend Scores      │
│  Hosted on Railway                                   │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌────────────┐ ┌─────────┐ ┌──────────────┐
   │ Next.js    │ │ Beehiiv │ │ OpenClaw +   │
   │ Dashboard  │ │ Newsletter│ │ Genviral     │
   │ (Vercel)   │ │ (API)   │ │ (Social)     │
   └────────────┘ └─────────┘ └──────────────┘
```

## Data Sources and Signal Weights

| Source | Signal | Weight | Update Frequency |
|--------|--------|--------|------------------|
| Yelp API | `hot_and_new` flag + review velocity | 30% | Every 6 hours |
| Reddit API | Mention count + upvotes in r/SFFood, r/bayarea, r/sanfrancisco | 25% | Every 6 hours |
| Threads API | Keyword mentions + engagement | 20% | Every 6 hours |
| Google Places | Review count acceleration + rating changes | 15% | Every 12 hours |
| Google Trends | Search interest for restaurant names in SF metro | 10% | Daily |

## Project Structure

```
sf-trending-eats/
├── pipeline/                 # Python data pipeline
│   ├── collectors/           # API collectors for each source
│   │   ├── yelp.py
│   │   ├── reddit.py
│   │   ├── threads.py
│   │   ├── google_places.py
│   │   └── google_trends.py
│   ├── scoring/              # Trend scoring engine
│   │   ├── engine.py
│   │   └── normalizer.py
│   ├── utils/                # Shared utilities
│   │   ├── db.py
│   │   ├── nlp.py
│   │   └── restaurant_matcher.py
│   ├── publisher.py          # Newsletter + social publishing
│   ├── run_collection.py     # Main collection entrypoint
│   └── run_weekly_publish.py # Weekly publish entrypoint
├── web/                      # Next.js dashboard
│   ├── app/
│   ├── components/
│   └── lib/
├── openclaw/                 # OpenClaw skill for social distribution
│   └── SKILL.md
├── db/                       # Database schema and migrations
│   └── schema.sql
├── config/                   # Configuration
│   └── settings.py
├── scripts/                  # Utility scripts
│   └── seed_subreddits.py
├── .github/workflows/        # GitHub Actions
│   ├── collect.yml
│   └── publish.yml
├── .env.example
├── requirements.txt
├── package.json
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 15+ with TimescaleDB extension
- API keys: Yelp, Reddit, Google Places, Google Trends

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/sf-trending-eats.git
cd sf-trending-eats

# Python dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Web dashboard
cd web
npm install
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys and database URL
```

### 3. Set up database

```bash
psql $DATABASE_URL < db/schema.sql
```

### 4. Run the pipeline

```bash
# Collect data from all sources
python pipeline/run_collection.py

# Compute trend scores
python pipeline/scoring/engine.py

# Publish weekly list
python pipeline/run_weekly_publish.py
```

### 5. Launch the dashboard

```bash
cd web
npm run dev
```

## API Keys Required

| Service | Free Tier | Estimated Monthly Cost |
|---------|-----------|----------------------|
| Yelp Fusion API | 5,000 calls/day | $0 (free tier sufficient) |
| Reddit API | 100 req/min (non-commercial) | $0 dev / ~$50 commercial |
| Google Places API | $200 free credit/month | $0 (within free tier) |
| Google Trends (pytrends) | Unofficial, rate limited | $0 |
| Threads API | Free | $0 |
| Beehiiv | Free up to 2,500 subscribers | $0 to start |
| Genviral (OpenClaw) | Starts at $29/month | $29 |

**Estimated total MVP cost: $30 to $80/month**

## OpenClaw Integration

The `openclaw/` directory contains a custom skill that automates social media distribution. Once configured, your OpenClaw agent can:

- Generate TikTok slideshow scripts from the weekly trending list
- Create Instagram carousel captions with trending data hooks
- Post to Threads with engagement stats
- Track post performance and feed analytics back into the pipeline

See [openclaw/SKILL.md](openclaw/SKILL.md) for setup instructions.

## Deployment

- **Pipeline**: GitHub Actions (scheduled cron) or Railway
- **Database**: Railway PostgreSQL with TimescaleDB
- **Dashboard**: Vercel (auto-deploy from main branch)
- **Newsletter**: Beehiiv (API-driven from pipeline)
- **Social**: OpenClaw on a VPS or local machine

## Roadmap

- [x] Multi-source data pipeline
- [x] Engagement velocity scoring
- [x] Web dashboard MVP
- [x] Newsletter automation
- [x] OpenClaw social distribution
- [ ] Neighborhood-level filtering
- [ ] Cuisine-type trending (e.g., "omakase is surging")
- [ ] User submissions and community voting
- [ ] Premium tier with daily alerts
- [ ] Mobile PWA
- [ ] Expansion to other cities

## Contributing

Pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT
