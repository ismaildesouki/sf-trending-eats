"""
Database connection and helper functions.
Uses psycopg2 with connection pooling.
"""

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from config import settings

logger = logging.getLogger(__name__)

# Connection pool (initialized lazily)
_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=settings.db.url,
        )
    return _pool


@contextmanager
def get_conn():
    """Get a connection from the pool, auto-return on exit."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def get_cursor(cursor_factory=None):
    """Get a cursor with optional factory (e.g., RealDictCursor)."""
    with get_conn() as conn:
        factory = cursor_factory or psycopg2.extras.RealDictCursor
        cur = conn.cursor(cursor_factory=factory)
        try:
            yield cur
        finally:
            cur.close()


# ============================================================
# Restaurant CRUD
# ============================================================

def upsert_restaurant(
    name: str,
    slug: str,
    neighborhood: str = None,
    cuisine_type: str = None,
    price_range: str = None,
    latitude: float = None,
    longitude: float = None,
    yelp_id: str = None,
    google_place_id: str = None,
    yelp_url: str = None,
    google_maps_url: str = None,
    image_url: str = None,
) -> int:
    """Insert or update a restaurant, return its ID."""
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO restaurants (
                name, slug, neighborhood, cuisine_type, price_range,
                latitude, longitude, yelp_id, google_place_id,
                yelp_url, google_maps_url, image_url, updated_at
            ) VALUES (
                %(name)s, %(slug)s, %(neighborhood)s, %(cuisine_type)s, %(price_range)s,
                %(latitude)s, %(longitude)s, %(yelp_id)s, %(google_place_id)s,
                %(yelp_url)s, %(google_maps_url)s, %(image_url)s, NOW()
            )
            ON CONFLICT (slug) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, restaurants.name),
                neighborhood = COALESCE(EXCLUDED.neighborhood, restaurants.neighborhood),
                cuisine_type = COALESCE(EXCLUDED.cuisine_type, restaurants.cuisine_type),
                price_range = COALESCE(EXCLUDED.price_range, restaurants.price_range),
                latitude = COALESCE(EXCLUDED.latitude, restaurants.latitude),
                longitude = COALESCE(EXCLUDED.longitude, restaurants.longitude),
                yelp_id = COALESCE(EXCLUDED.yelp_id, restaurants.yelp_id),
                google_place_id = COALESCE(EXCLUDED.google_place_id, restaurants.google_place_id),
                yelp_url = COALESCE(EXCLUDED.yelp_url, restaurants.yelp_url),
                google_maps_url = COALESCE(EXCLUDED.google_maps_url, restaurants.google_maps_url),
                image_url = COALESCE(EXCLUDED.image_url, restaurants.image_url),
                updated_at = NOW()
            RETURNING id
        """, {
            "name": name, "slug": slug, "neighborhood": neighborhood,
            "cuisine_type": cuisine_type, "price_range": price_range,
            "latitude": latitude, "longitude": longitude,
            "yelp_id": yelp_id, "google_place_id": google_place_id,
            "yelp_url": yelp_url, "google_maps_url": google_maps_url,
            "image_url": image_url,
        })
        return cur.fetchone()["id"]


def find_restaurant_by_name(name: str) -> dict | None:
    """Fuzzy match a restaurant name, return the best match or None."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT *, similarity(name, %(name)s) AS sim
            FROM restaurants
            WHERE similarity(name, %(name)s) > 0.3
            ORDER BY sim DESC
            LIMIT 1
        """, {"name": name})
        return cur.fetchone()


def get_restaurant_by_slug(slug: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM restaurants WHERE slug = %s", (slug,))
        return cur.fetchone()


# ============================================================
# Mentions
# ============================================================

def insert_mention(
    restaurant_id: int,
    platform: str,
    source_id: str = None,
    source_url: str = None,
    content_snippet: str = None,
    engagement: dict = None,
    sentiment_score: float = None,
    author_reach: int = 0,
    metadata: dict = None,
    time: datetime = None,
):
    """Insert a social media mention."""
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO mentions (
                time, restaurant_id, platform, source_id, source_url,
                content_snippet, engagement, sentiment_score,
                author_reach, metadata
            ) VALUES (
                %(time)s, %(restaurant_id)s, %(platform)s, %(source_id)s,
                %(source_url)s, %(content_snippet)s, %(engagement)s,
                %(sentiment_score)s, %(author_reach)s, %(metadata)s
            )
            ON CONFLICT DO NOTHING
        """, {
            "time": time or datetime.now(timezone.utc),
            "restaurant_id": restaurant_id,
            "platform": platform,
            "source_id": source_id,
            "source_url": source_url,
            "content_snippet": (content_snippet or "")[:500],
            "engagement": json.dumps(engagement or {}),
            "sentiment_score": sentiment_score,
            "author_reach": author_reach,
            "metadata": json.dumps(metadata or {}),
        })


def insert_mention_batch(mentions: list[dict]):
    """Bulk insert mentions for efficiency."""
    if not mentions:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO mentions (
                    time, restaurant_id, platform, source_id, source_url,
                    content_snippet, engagement, sentiment_score,
                    author_reach, metadata
                ) VALUES %s
                ON CONFLICT DO NOTHING
                """,
                [
                    (
                        m.get("time", datetime.now(timezone.utc)),
                        m["restaurant_id"],
                        m["platform"],
                        m.get("source_id"),
                        m.get("source_url"),
                        (m.get("content_snippet") or "")[:500],
                        json.dumps(m.get("engagement", {})),
                        m.get("sentiment_score"),
                        m.get("author_reach", 0),
                        json.dumps(m.get("metadata", {})),
                    )
                    for m in mentions
                ],
            )


# ============================================================
# Trend Scores
# ============================================================

def insert_trend_scores(scores: list[dict]):
    """Insert computed trend scores for a batch of restaurants."""
    if not scores:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO trend_scores (
                    time, restaurant_id, score, rank,
                    mention_velocity_score, engagement_accel_score,
                    cross_platform_score, sentiment_score,
                    influencer_signal_score, platforms_active,
                    trending_reason, metadata
                ) VALUES %s
                """,
                [
                    (
                        s.get("time", datetime.now(timezone.utc)),
                        s["restaurant_id"],
                        s["score"],
                        s.get("rank"),
                        s.get("mention_velocity_score", 0),
                        s.get("engagement_accel_score", 0),
                        s.get("cross_platform_score", 0),
                        s.get("sentiment_score", 0),
                        s.get("influencer_signal_score", 0),
                        s.get("platforms_active", []),
                        s.get("trending_reason"),
                        json.dumps(s.get("metadata", {})),
                    )
                    for s in scores
                ],
            )


def get_latest_trending(n: int = 10) -> list[dict]:
    """Get the most recent top N trending restaurants."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT * FROM get_trending_restaurants(%(n)s)
        """, {"n": n})
        return cur.fetchall()


# ============================================================
# Weekly Lists
# ============================================================

def create_weekly_list(week_start, restaurant_ids: list[int]) -> int:
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO weekly_lists (week_start, restaurant_ids, status)
            VALUES (%(week_start)s, %(restaurant_ids)s, 'draft')
            ON CONFLICT (week_start) DO UPDATE SET
                restaurant_ids = EXCLUDED.restaurant_ids,
                status = 'draft'
            RETURNING id
        """, {"week_start": week_start, "restaurant_ids": restaurant_ids})
        return cur.fetchone()["id"]


def mark_list_published(list_id: int, newsletter_url: str = None):
    with get_cursor() as cur:
        cur.execute("""
            UPDATE weekly_lists
            SET status = 'published', published_at = NOW(), newsletter_url = %(url)s
            WHERE id = %(id)s
        """, {"id": list_id, "url": newsletter_url})
