-- SF Trending Eats Database Schema
-- Requires PostgreSQL 15+ with TimescaleDB extension

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================
-- CORE TABLES
-- ============================================================

-- Canonical restaurant records (deduplicated across sources)
CREATE TABLE restaurants (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    slug            TEXT UNIQUE NOT NULL,
    neighborhood    TEXT,
    city            TEXT DEFAULT 'San Francisco',
    cuisine_type    TEXT,
    price_range     TEXT,           -- $, $$, $$$, $$$$
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    yelp_id         TEXT UNIQUE,
    google_place_id TEXT UNIQUE,
    yelp_url        TEXT,
    google_maps_url TEXT,
    image_url       TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    first_seen_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_restaurants_neighborhood ON restaurants(neighborhood);
CREATE INDEX idx_restaurants_cuisine ON restaurants(cuisine_type);
CREATE INDEX idx_restaurants_slug ON restaurants(slug);

-- ============================================================
-- TIME SERIES TABLES (TimescaleDB hypertables)
-- ============================================================

-- Individual social media mentions
CREATE TABLE mentions (
    time            TIMESTAMPTZ NOT NULL,
    restaurant_id   INTEGER NOT NULL REFERENCES restaurants(id),
    platform        TEXT NOT NULL,       -- yelp, reddit, threads, google, trends
    source_id       TEXT,                -- platform-specific post/review ID
    source_url      TEXT,
    content_snippet TEXT,                -- first 500 chars, anonymized
    engagement      JSONB DEFAULT '{}',  -- {likes, comments, shares, views, upvotes}
    sentiment_score REAL,                -- -1.0 to 1.0
    author_reach    INTEGER DEFAULT 0,   -- follower/karma count (anonymized)
    metadata        JSONB DEFAULT '{}'
);

SELECT create_hypertable('mentions', 'time');
CREATE INDEX idx_mentions_restaurant ON mentions(restaurant_id, time DESC);
CREATE INDEX idx_mentions_platform ON mentions(platform, time DESC);

-- Periodic engagement snapshots (computed every 6 hours)
CREATE TABLE engagement_snapshots (
    time            TIMESTAMPTZ NOT NULL,
    restaurant_id   INTEGER NOT NULL REFERENCES restaurants(id),
    platform        TEXT NOT NULL,
    mention_count   INTEGER DEFAULT 0,      -- mentions in this period
    total_engagement INTEGER DEFAULT 0,     -- sum of all engagement signals
    avg_sentiment   REAL DEFAULT 0.0,
    max_author_reach INTEGER DEFAULT 0,
    engagement_velocity REAL DEFAULT 0.0,   -- rate of change
    metadata        JSONB DEFAULT '{}'
);

SELECT create_hypertable('engagement_snapshots', 'time');
CREATE INDEX idx_snapshots_restaurant ON engagement_snapshots(restaurant_id, time DESC);

-- Computed trend scores (the product's core output)
CREATE TABLE trend_scores (
    time            TIMESTAMPTZ NOT NULL,
    restaurant_id   INTEGER NOT NULL REFERENCES restaurants(id),
    score           REAL NOT NULL,          -- composite trend score
    rank            INTEGER,                -- position in weekly ranking
    mention_velocity_score  REAL DEFAULT 0.0,   -- 30% weight
    engagement_accel_score  REAL DEFAULT 0.0,   -- 25% weight
    cross_platform_score    REAL DEFAULT 0.0,   -- 20% weight
    sentiment_score         REAL DEFAULT 0.0,   -- 15% weight
    influencer_signal_score REAL DEFAULT 0.0,   -- 10% weight
    platforms_active        TEXT[] DEFAULT '{}', -- which platforms have signal
    trending_reason         TEXT,                -- AI-generated explanation
    metadata                JSONB DEFAULT '{}'
);

SELECT create_hypertable('trend_scores', 'time');
CREATE INDEX idx_trend_scores_rank ON trend_scores(time DESC, rank ASC);
CREATE INDEX idx_trend_scores_restaurant ON trend_scores(restaurant_id, time DESC);

-- ============================================================
-- PUBLISHING TABLES
-- ============================================================

-- Weekly published lists
CREATE TABLE weekly_lists (
    id              SERIAL PRIMARY KEY,
    week_start      DATE NOT NULL UNIQUE,
    published_at    TIMESTAMPTZ,
    newsletter_url  TEXT,
    status          TEXT DEFAULT 'draft', -- draft, published, failed
    restaurant_ids  INTEGER[],           -- ordered list of restaurant IDs
    metadata        JSONB DEFAULT '{}'
);

-- Social media posts tracking
CREATE TABLE social_posts (
    id              SERIAL PRIMARY KEY,
    weekly_list_id  INTEGER REFERENCES weekly_lists(id),
    platform        TEXT NOT NULL,
    post_url        TEXT,
    posted_at       TIMESTAMPTZ,
    engagement      JSONB DEFAULT '{}',  -- tracked performance
    status          TEXT DEFAULT 'draft',
    content         TEXT,
    metadata        JSONB DEFAULT '{}'
);

-- ============================================================
-- CONTINUOUS AGGREGATES (auto-computed by TimescaleDB)
-- ============================================================

-- Rolling 24-hour mention counts per restaurant per platform
CREATE MATERIALIZED VIEW mention_counts_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    restaurant_id,
    platform,
    COUNT(*) AS mention_count,
    AVG(sentiment_score) AS avg_sentiment,
    SUM((engagement->>'likes')::int) AS total_likes,
    SUM((engagement->>'comments')::int) AS total_comments
FROM mentions
GROUP BY bucket, restaurant_id, platform;

-- Refresh policy: update every hour, look back 2 hours
SELECT add_continuous_aggregate_policy('mention_counts_hourly',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

-- Rolling 7-day aggregates for trend computation
CREATE MATERIALIZED VIEW mention_counts_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    restaurant_id,
    platform,
    COUNT(*) AS mention_count,
    AVG(sentiment_score) AS avg_sentiment,
    MAX(author_reach) AS max_reach
FROM mentions
GROUP BY bucket, restaurant_id, platform;

SELECT add_continuous_aggregate_policy('mention_counts_daily',
    start_offset => INTERVAL '2 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day'
);

-- ============================================================
-- DATA RETENTION
-- ============================================================

-- Keep raw mentions for 90 days, aggregates forever
SELECT add_retention_policy('mentions', INTERVAL '90 days');

-- ============================================================
-- HELPER FUNCTIONS
-- ============================================================

-- Get the latest trend score for each restaurant, ranked
CREATE OR REPLACE FUNCTION get_trending_restaurants(n INTEGER DEFAULT 10)
RETURNS TABLE (
    restaurant_id INTEGER,
    name TEXT,
    neighborhood TEXT,
    cuisine_type TEXT,
    score REAL,
    rank INTEGER,
    trending_reason TEXT,
    platforms_active TEXT[],
    scored_at TIMESTAMPTZ
) AS $$
    SELECT
        r.id,
        r.name,
        r.neighborhood,
        r.cuisine_type,
        ts.score,
        ts.rank,
        ts.trending_reason,
        ts.platforms_active,
        ts.time AS scored_at
    FROM trend_scores ts
    JOIN restaurants r ON r.id = ts.restaurant_id
    WHERE ts.time = (SELECT MAX(time) FROM trend_scores)
    ORDER BY ts.rank ASC
    LIMIT n;
$$ LANGUAGE sql STABLE;
