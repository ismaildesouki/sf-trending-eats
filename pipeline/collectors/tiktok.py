"""
TikTok hashtag collector via Apify.

Uses the clockworks/tiktok-hashtag-scraper Apify actor to collect
trending TikTok videos about SF Bay Area restaurants by hashtag.

Primary signals:
  - Play count (viral reach)
  - Engagement (likes, shares, comments)
  - Creator follower count (influencer signal)

Apify free tier: ~$5-15/mo depending on volume.
Actor: https://apify.com/clockworks/tiktok-hashtag-scraper
"""

import asyncio
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
from pipeline.utils.db import (
    upsert_restaurant,
    insert_mention,
    insert_mention_batch,
    get_cursor,
)

logger = logging.getLogger(__name__)

ACTOR_ID = "clockworks/tiktok-hashtag-scraper"


def _get_known_restaurant_names() -> list[str]:
    """Load known restaurant names from DB for matching."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT name FROM restaurants WHERE is_active = TRUE")
            return [row["name"] for row in cur.fetchall()]
    except Exception as e:
        logger.warning(f"Could not load known restaurant names: {e}")
        return []


def _parse_video(item: dict) -> dict | None:
    """
    Parse a TikTok video item from the Apify scraper into our standard format.
    Returns None if the item cannot be parsed.
    """
    try:
        video_id = item.get("id") or item.get("videoId")
        if not video_id:
            return None

        # Caption text — the scraper uses different field names
        caption = (
            item.get("text")
            or item.get("desc")
            or item.get("description")
            or ""
        )

        # Engagement stats — handle both flat and nested formats
        stats = item.get("stats") or item.get("videoMeta") or {}
        likes = (
            stats.get("diggCount")
            or stats.get("likeCount")
            or item.get("diggCount")
            or 0
        )
        shares = (
            stats.get("shareCount")
            or item.get("shareCount")
            or 0
        )
        comments = (
            stats.get("commentCount")
            or item.get("commentCount")
            or 0
        )
        plays = (
            stats.get("playCount")
            or item.get("playCount")
            or 0
        )

        # Author info — handle both flat and nested formats
        author_meta = item.get("authorMeta") or item.get("author") or {}
        if isinstance(author_meta, str):
            # Sometimes "author" is just the username string
            author_username = author_meta
            author_followers = 0
        else:
            author_username = (
                author_meta.get("name")
                or author_meta.get("uniqueId")
                or author_meta.get("nickname")
                or ""
            )
            author_followers = (
                author_meta.get("fans")
                or author_meta.get("followers")
                or author_meta.get("followerCount")
                or 0
            )

        # Video URL
        video_url = (
            item.get("webVideoUrl")
            or item.get("videoUrl")
            or item.get("url")
            or ""
        )

        # Timestamp
        create_time = item.get("createTime") or item.get("createTimeISO")
        if isinstance(create_time, (int, float)):
            video_time = datetime.fromtimestamp(create_time, tz=timezone.utc)
        elif isinstance(create_time, str):
            try:
                video_time = datetime.fromisoformat(create_time.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                video_time = datetime.now(timezone.utc)
        else:
            video_time = datetime.now(timezone.utc)

        # Hashtags
        hashtags_raw = item.get("hashtags") or []
        if hashtags_raw and isinstance(hashtags_raw[0], dict):
            hashtags = [h.get("name", "") for h in hashtags_raw]
        else:
            hashtags = [str(h) for h in hashtags_raw]

        return {
            "video_id": str(video_id),
            "caption": caption,
            "likes": likes,
            "shares": shares,
            "comments": comments,
            "plays": plays,
            "author_username": author_username,
            "author_followers": author_followers,
            "video_url": video_url,
            "time": video_time,
            "hashtags": hashtags,
        }

    except Exception as e:
        logger.warning(f"Failed to parse TikTok video item: {e}")
        return None


def _scrape_hashtag(apify_client: ApifyClient, hashtag: str, max_results: int) -> list[dict]:
    """
    Run the Apify TikTok hashtag scraper for a single hashtag.
    This is a blocking call (Apify actor runs synchronously).
    """
    try:
        run_input = {
            "hashtags": [hashtag],
            "resultsPerPage": max_results,
        }

        logger.info(f"TikTok: scraping #{hashtag} (max {max_results} results)...")
        run = apify_client.actor(ACTOR_ID).call(run_input=run_input)

        items = list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())
        logger.info(f"TikTok: #{hashtag} returned {len(items)} videos")
        return items

    except Exception as e:
        logger.error(f"TikTok: Apify scrape for #{hashtag} failed: {e}")
        return []


async def run(client: httpx.AsyncClient = None) -> dict:
    """
    Main entry point for TikTok collection.

    Uses the Apify TikTok hashtag scraper to collect videos, then attempts
    to extract restaurant names from captions using NLP.

    Args:
        client: Optional httpx client (not used directly, kept for interface
                consistency with other collectors).

    Returns:
        Summary stats dict.
    """
    stats = {
        "videos_collected": 0,
        "restaurants_matched": 0,
        "mentions_created": 0,
        "unresolved": 0,
        "hashtags_scraped": 0,
    }

    # Validate config
    token = settings.tiktok.apify_token
    if not token:
        logger.error("TikTok: APIFY_TOKEN not configured, skipping collection")
        return stats

    apify_client = ApifyClient(token)
    hashtags = settings.tiktok.hashtags
    results_per_hashtag = settings.tiktok.results_per_hashtag

    # Load known restaurant names for matching
    known_names = _get_known_restaurant_names()

    # Collect videos from all hashtags
    # Apify actor .call() is blocking, so run in executor to avoid blocking event loop
    loop = asyncio.get_event_loop()
    all_items = []
    for hashtag in hashtags:
        try:
            items = await loop.run_in_executor(
                None, _scrape_hashtag, apify_client, hashtag, results_per_hashtag
            )
            all_items.extend(items)
            stats["hashtags_scraped"] += 1
        except Exception as e:
            logger.error(f"TikTok: failed to scrape #{hashtag}: {e}")

    # Parse and deduplicate videos
    seen_ids = set()
    parsed_videos = []

    for item in all_items:
        video = _parse_video(item)
        if video is None:
            continue
        if video["video_id"] in seen_ids:
            continue
        seen_ids.add(video["video_id"])
        parsed_videos.append(video)

    stats["videos_collected"] = len(parsed_videos)
    logger.info(f"TikTok: collected {stats['videos_collected']} unique videos from {stats['hashtags_scraped']} hashtags")

    # Process each video: extract restaurant names, create mentions
    resolved_mentions = []
    unresolved_mentions = []

    for video in parsed_videos:
        caption = video["caption"]

        # Skip non-food-related content
        if not is_food_related(caption):
            continue

        # Build engagement dict
        engagement = {
            "likes": video["likes"],
            "shares": video["shares"],
            "comments": video["comments"],
            "plays": video["plays"],
        }

        # Sentiment analysis on caption
        sentiment = analyze_sentiment(caption)

        # Build metadata
        metadata = {
            "hashtags": video["hashtags"],
            "author_username": video["author_username"],
        }

        # Try to extract restaurant names from caption
        names = extract_restaurant_names(caption, known_names)

        if names:
            # Restaurant name(s) found — create a mention for each
            for name in names:
                slug = generate_slug(name)
                restaurant_id = upsert_restaurant(name=name, slug=slug)

                resolved_mentions.append({
                    "restaurant_id": restaurant_id,
                    "platform": "tiktok",
                    "source_id": video["video_id"],
                    "source_url": video["video_url"],
                    "content_snippet": caption[:500],
                    "engagement": engagement,
                    "sentiment_score": sentiment,
                    "author_reach": video["author_followers"],
                    "metadata": metadata,
                    "time": video["time"],
                })

                stats["restaurants_matched"] += 1
        else:
            # No restaurant name resolved — store for later entity resolution
            # These will be processed when the entity_resolver is integrated
            unresolved_mentions.append({
                "restaurant_id": None,
                "platform": "tiktok",
                "source_id": video["video_id"],
                "source_url": video["video_url"],
                "content_snippet": caption[:500],
                "engagement": engagement,
                "sentiment_score": sentiment,
                "author_reach": video["author_followers"],
                "metadata": {
                    **metadata,
                    "needs_entity_resolution": True,
                },
                "time": video["time"],
            })
            stats["unresolved"] += 1

    # Persist resolved mentions in bulk
    if resolved_mentions:
        insert_mention_batch(resolved_mentions)
        stats["mentions_created"] += len(resolved_mentions)

    # Log unresolved for visibility (these will be handled by entity_resolver later)
    if unresolved_mentions:
        logger.info(
            f"TikTok: {len(unresolved_mentions)} videos could not be matched to "
            f"a restaurant — will need entity resolution"
        )

    logger.info(f"TikTok collection complete: {stats}")
    return stats
