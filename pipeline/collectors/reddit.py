"""
Reddit API collector.

Monitors Bay Area food subreddits for restaurant mentions.
Primary signals: upvotes, comment count, post frequency.

Uses OAuth2 with the free tier (100 req/min, non-commercial).
For commercial use, apply at: https://www.reddit.com/wiki/api

Docs: https://www.reddit.com/dev/api
"""

import logging
from datetime import datetime, timezone

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

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
BASE_URL = "https://oauth.reddit.com"


async def _get_access_token(client: httpx.AsyncClient) -> str:
    """Obtain OAuth2 access token using client credentials."""
    resp = await client.post(
        TOKEN_URL,
        auth=(settings.reddit.client_id, settings.reddit.client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": settings.reddit.user_agent},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _get_known_restaurant_names() -> list[str]:
    """Load known restaurant names from the Google Sheet."""
    return get_all_restaurant_names()


async def collect_subreddit(
    client: httpx.AsyncClient,
    headers: dict,
    subreddit: str,
    known_names: list[str],
) -> list[dict]:
    """
    Collect food-related posts from a single subreddit.
    Scans both hot and new listings.
    """
    mentions = []

    for listing in ["hot", "new"]:
        try:
            url = f"{BASE_URL}/r/{subreddit}/{listing}"
            params = {"limit": settings.reddit.posts_per_sub}
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

            for post in data.get("data", {}).get("children", []):
                post_data = post.get("data", {})

                # Combine title and selftext for analysis
                text = f"{post_data.get('title', '')} {post_data.get('selftext', '')}"

                # Filter: only food-related posts
                if not is_food_related(text):
                    continue

                # Extract restaurant names
                names = extract_restaurant_names(text, known_names)
                if not names:
                    continue

                # Build mention for each restaurant found
                for name in names:
                    mentions.append({
                        "restaurant_name": name,
                        "platform": "reddit",
                        "source_id": post_data.get("id"),
                        "source_url": f"https://reddit.com{post_data.get('permalink', '')}",
                        "content_snippet": text[:500],
                        "engagement": {
                            "upvotes": post_data.get("ups", 0),
                            "comments": post_data.get("num_comments", 0),
                            "upvote_ratio": post_data.get("upvote_ratio", 0),
                            "score": post_data.get("score", 0),
                        },
                        "sentiment_score": analyze_sentiment(text),
                        "author_reach": 0,  # Reddit doesn't expose karma easily
                        "metadata": {
                            "subreddit": subreddit,
                            "listing": listing,
                            "flair": post_data.get("link_flair_text"),
                        },
                        "time": datetime.fromtimestamp(
                            post_data.get("created_utc", 0), tz=timezone.utc
                        ),
                    })

        except httpx.HTTPStatusError as e:
            logger.warning(f"Reddit r/{subreddit}/{listing} error: {e.response.status_code}")
        except Exception as e:
            logger.warning(f"Reddit r/{subreddit}/{listing} failed: {e}")

    return mentions


async def collect_comments_for_post(
    client: httpx.AsyncClient,
    headers: dict,
    subreddit: str,
    post_id: str,
    known_names: list[str],
) -> list[dict]:
    """Scan comments on a high-engagement post for additional restaurant mentions."""
    mentions = []

    try:
        url = f"{BASE_URL}/r/{subreddit}/comments/{post_id}"
        params = {"limit": 100, "depth": 2, "sort": "top"}
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        # Comments are in the second listing
        if len(data) >= 2:
            for comment in data[1].get("data", {}).get("children", []):
                comment_data = comment.get("data", {})
                body = comment_data.get("body", "")

                if not is_food_related(body):
                    continue

                names = extract_restaurant_names(body, known_names)
                for name in names:
                    mentions.append({
                        "restaurant_name": name,
                        "platform": "reddit",
                        "source_id": comment_data.get("id"),
                        "source_url": f"https://reddit.com{comment_data.get('permalink', '')}",
                        "content_snippet": body[:500],
                        "engagement": {
                            "upvotes": comment_data.get("ups", 0),
                            "score": comment_data.get("score", 0),
                        },
                        "sentiment_score": analyze_sentiment(body),
                        "metadata": {
                            "subreddit": subreddit,
                            "type": "comment",
                            "parent_id": post_id,
                        },
                        "time": datetime.fromtimestamp(
                            comment_data.get("created_utc", 0), tz=timezone.utc
                        ),
                    })

    except Exception as e:
        logger.warning(f"Reddit comments for {post_id} failed: {e}")

    return mentions


async def run(client: httpx.AsyncClient = None) -> dict:
    """Main entry point for Reddit collection."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30)

    try:
        stats = {"subreddits_scanned": 0, "posts_scanned": 0, "mentions_found": 0}

        # Authenticate
        token = await _get_access_token(client)
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": settings.reddit.user_agent,
        }

        # Load known restaurants for name matching
        known_names = _get_known_restaurant_names()

        # Scan each subreddit
        all_mentions = []
        for sub in settings.reddit.subreddits:
            mentions = await collect_subreddit(client, headers, sub, known_names)
            all_mentions.extend(mentions)
            stats["subreddits_scanned"] += 1

        stats["mentions_found"] = len(all_mentions)

        # Resolve restaurant names to IDs and persist
        db_mentions = []
        for mention in all_mentions:
            name = mention.pop("restaurant_name")
            slug = generate_slug(name)

            # Upsert restaurant (will create new ones discovered via Reddit)
            restaurant_id = upsert_restaurant(name=name, slug=slug)
            mention["restaurant_id"] = restaurant_id
            db_mentions.append(mention)

        insert_mention_batch(db_mentions)

        logger.info(f"Reddit collection complete: {stats}")
        return stats

    finally:
        if own_client:
            await client.aclose()
