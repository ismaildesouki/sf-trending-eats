"""
Meta Threads API collector.

Uses the Threads API keyword search (added July 2025) to find
restaurant mentions in the Bay Area.

Primary signals: likes, replies, reposts.
Free tier, no rate limit published (use conservative pacing).

Docs: https://developers.facebook.com/docs/threads
"""

import logging
from datetime import datetime, timezone, timedelta

import httpx

from config import settings
from pipeline.utils.nlp import (
    analyze_sentiment,
    extract_restaurant_names,
    is_food_related,
    generate_slug,
)
from pipeline.utils.db import upsert_restaurant, insert_mention_batch, get_all_restaurant_names

logger = logging.getLogger(__name__)

THREADS_SEARCH_URL = "https://graph.threads.net/v1.0/search"


def _get_known_restaurant_names() -> list[str]:
    """Load known restaurant names from the Google Sheet."""
    return get_all_restaurant_names()


async def search_keyword(
    client: httpx.AsyncClient,
    keyword: str,
    known_names: list[str],
) -> list[dict]:
    """
    Search Threads for posts matching a keyword.
    The Threads API supports keyword search with date ranges.
    """
    mentions = []

    try:
        # Search posts from the last 7 days
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        params = {
            "q": keyword,
            "since": since,
            "fields": "id,text,timestamp,like_count,reply_count,repost_count,username",
            "access_token": settings.threads.access_token,
            "limit": 50,
        }

        resp = await client.get(THREADS_SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        for post in data.get("data", []):
            text = post.get("text", "")

            if not is_food_related(text):
                continue

            names = extract_restaurant_names(text, known_names)
            if not names:
                continue

            for name in names:
                mentions.append({
                    "restaurant_name": name,
                    "platform": "threads",
                    "source_id": post.get("id"),
                    "source_url": f"https://threads.net/@{post.get('username', '')}/post/{post.get('id', '')}",
                    "content_snippet": text[:500],
                    "engagement": {
                        "likes": post.get("like_count", 0),
                        "replies": post.get("reply_count", 0),
                        "reposts": post.get("repost_count", 0),
                    },
                    "sentiment_score": analyze_sentiment(text),
                    "author_reach": 0,  # Would need separate user lookup
                    "metadata": {
                        "keyword": keyword,
                        "username": post.get("username"),
                    },
                    "time": datetime.fromisoformat(
                        post.get("timestamp", datetime.now(timezone.utc).isoformat())
                    ),
                })

    except httpx.HTTPStatusError as e:
        logger.warning(f"Threads search '{keyword}' error: {e.response.status_code}")
    except Exception as e:
        logger.warning(f"Threads search '{keyword}' failed: {e}")

    return mentions


async def run(client: httpx.AsyncClient = None) -> dict:
    """Main entry point for Threads collection."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30)

    try:
        stats = {"keywords_searched": 0, "mentions_found": 0}

        known_names = _get_known_restaurant_names()
        all_mentions = []

        for keyword in settings.threads.keywords:
            mentions = await search_keyword(client, keyword, known_names)
            all_mentions.extend(mentions)
            stats["keywords_searched"] += 1

        stats["mentions_found"] = len(all_mentions)

        # Resolve and persist
        db_mentions = []
        for mention in all_mentions:
            name = mention.pop("restaurant_name")
            slug = generate_slug(name)
            restaurant_id = upsert_restaurant(name=name, slug=slug)
            mention["restaurant_id"] = restaurant_id
            db_mentions.append(mention)

        insert_mention_batch(db_mentions)

        logger.info(f"Threads collection complete: {stats}")
        return stats

    finally:
        if own_client:
            await client.aclose()
