"""
Instagram hashtag collector via Apify.

Scrapes Instagram posts by SF food hashtags using the
apify/instagram-hashtag-scraper actor. Extracts restaurant mentions from
both captions (NLP) and tagged locations (high-confidence signal).

Apify free tier runs are billed per compute unit (~$5-15/mo at our volume).
Docs: https://apify.com/apify/instagram-hashtag-scraper
"""

import logging
from datetime import datetime, timezone

import httpx
from apify_client import ApifyClient

from config import settings
from pipeline.utils.nlp import (
    analyze_sentiment,
    extract_restaurant_names,
    is_food_related,
    generate_slug,
)
from pipeline.utils.db import upsert_restaurant, insert_mention, get_cursor

logger = logging.getLogger(__name__)

ACTOR_ID = "apify/instagram-hashtag-scraper"


def _get_known_restaurant_names() -> list[str]:
    """Load known restaurant names from DB for matching."""
    with get_cursor() as cur:
        cur.execute("SELECT name FROM restaurants WHERE is_active = TRUE")
        return [row["name"] for row in cur.fetchall()]


def _build_engagement(item: dict) -> dict:
    """Build the engagement JSONB payload from an Instagram post item."""
    engagement = {
        "likes": item.get("likesCount", 0),
        "comments": item.get("commentsCount", 0),
    }
    views = item.get("videoViewCount") or item.get("videoPlayCount")
    if views:
        engagement["views"] = views
    return engagement


def _build_metadata(item: dict) -> dict:
    """Build the metadata JSONB payload from an Instagram post item."""
    meta = {
        "post_type": item.get("type"),
        "hashtags": item.get("hashtags", []),
    }
    location_name = item.get("locationName")
    if location_name:
        meta["location_name"] = location_name
    return meta


def _parse_timestamp(item: dict) -> datetime:
    """Parse the ISO timestamp from an Instagram post, fallback to now."""
    ts = item.get("timestamp")
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, AttributeError):
            pass
    return datetime.now(timezone.utc)


def _scrape_hashtag(apify_client: ApifyClient, hashtag: str, limit: int) -> list[dict]:
    """
    Run the Apify Instagram hashtag scraper for a single hashtag.
    This is a blocking call that waits for the actor run to finish.
    """
    run_input = {
        "hashtags": [hashtag],
        "resultsType": "posts",
        "resultsLimit": limit,
    }

    logger.info(f"Instagram: scraping #{hashtag} (limit={limit})")

    try:
        run = apify_client.actor(ACTOR_ID).call(run_input=run_input)
        items = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
        logger.info(f"Instagram: #{hashtag} returned {len(items)} posts")
        return items
    except Exception as e:
        logger.error(f"Instagram: Apify scrape failed for #{hashtag}: {e}")
        return []


async def run(client: httpx.AsyncClient = None) -> dict:
    """
    Main entry point for Instagram collection.

    Scrapes Instagram posts by SF food hashtags via Apify, extracts
    restaurant names from captions and location tags, then upserts
    restaurants and inserts mentions.

    Returns summary stats dict.
    """
    stats = {
        "posts_collected": 0,
        "restaurants_matched": 0,
        "from_location_tag": 0,
        "from_caption": 0,
    }

    if not settings.instagram.apify_token:
        logger.warning("Instagram: APIFY_TOKEN not set, skipping collection")
        return stats

    apify_client = ApifyClient(settings.instagram.apify_token)
    known_names = _get_known_restaurant_names()

    seen_ids: set[str] = set()
    hashtags = settings.instagram.hashtags
    limit = settings.instagram.results_per_hashtag

    for hashtag in hashtags:
        items = _scrape_hashtag(apify_client, hashtag, limit)

        for item in items:
            post_id = item.get("id")
            if not post_id or post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            stats["posts_collected"] += 1

            caption = item.get("caption") or ""
            location_name = item.get("locationName")

            # --- Identify restaurant names ---
            # Two strategies: location tag (high confidence) and caption NLP

            restaurant_names: list[str] = []
            name_sources: dict[str, str] = {}  # name -> source

            # Strategy 1: Location tag — if a food post is tagged at a
            # restaurant location, that's essentially a confirmed mention.
            if location_name:
                restaurant_names.append(location_name)
                name_sources[location_name.lower()] = "location_tag"

            # Strategy 2: Extract names from caption text via NLP
            if caption:
                caption_names = extract_restaurant_names(caption, known_names)
                for name in caption_names:
                    if name.lower() not in name_sources:
                        restaurant_names.append(name)
                        name_sources[name.lower()] = "caption"

            if not restaurant_names:
                continue

            # --- Build shared mention fields ---
            engagement = _build_engagement(item)
            metadata = _build_metadata(item)
            sentiment = analyze_sentiment(caption)
            post_time = _parse_timestamp(item)

            # --- Persist each restaurant mention ---
            for name in restaurant_names:
                source = name_sources.get(name.lower(), "caption")
                slug = generate_slug(name)

                try:
                    restaurant_id = upsert_restaurant(
                        name=name,
                        slug=slug,
                    )

                    insert_mention(
                        restaurant_id=restaurant_id,
                        platform="instagram",
                        source_id=post_id,
                        source_url=item.get("url"),
                        content_snippet=caption[:500] if caption else None,
                        engagement=engagement,
                        sentiment_score=sentiment,
                        author_reach=0,
                        metadata={
                            **metadata,
                            "owner_username": item.get("ownerUsername"),
                            "match_source": source,
                        },
                        time=post_time,
                    )

                    stats["restaurants_matched"] += 1
                    if source == "location_tag":
                        stats["from_location_tag"] += 1
                    else:
                        stats["from_caption"] += 1

                except Exception as e:
                    logger.warning(
                        f"Instagram: failed to persist mention for "
                        f"'{name}' (post {post_id}): {e}"
                    )

    logger.info(f"Instagram collection complete: {stats}")
    return stats
