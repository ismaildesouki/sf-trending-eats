"""
Yelp Fusion API collector.

Primary signals:
  - hot_and_new attribute (Yelp's own trending flag)
  - Review count velocity (delta over time)
  - Rating changes

Yelp free tier: 5,000 API calls/day (more than sufficient)
Docs: https://docs.developer.yelp.com/reference/v3_business_search
"""

import logging
from datetime import datetime, timezone

import httpx

from config import settings
from pipeline.utils.nlp import generate_slug, analyze_sentiment
from pipeline.utils.db import upsert_restaurant, insert_mention

logger = logging.getLogger(__name__)

YELP_SEARCH_URL = f"{settings.yelp.base_url}/businesses/search"
YELP_REVIEWS_URL = f"{settings.yelp.base_url}/businesses/{{biz_id}}/reviews"

HEADERS = {
    "Authorization": f"Bearer {settings.yelp.api_key}",
    "Accept": "application/json",
}

# Cuisine categories to scan (Yelp category aliases)
CUISINE_CATEGORIES = [
    "restaurants",
    "newamerican",
    "japanese",
    "chinese",
    "mexican",
    "italian",
    "korean",
    "thai",
    "vietnamese",
    "indian",
    "mediterranean",
    "seafood",
    "pizza",
    "burgers",
    "ramen",
    "sushi",
    "dimsum",
    "bakeries",
    "coffee",
    "cocktailbars",
]


async def collect_hot_and_new(client: httpx.AsyncClient) -> list[dict]:
    """
    Fetch restaurants with Yelp's hot_and_new attribute.
    This is the single most valuable signal in the entire pipeline.
    """
    results = []

    params = {
        "location": settings.yelp.location,
        "radius": settings.yelp.radius,
        "limit": settings.yelp.search_limit,
        "sort_by": "rating",
        "attributes": "hot_and_new",
    }

    try:
        resp = await client.get(YELP_SEARCH_URL, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()

        for biz in data.get("businesses", []):
            results.append(_parse_business(biz, is_hot_and_new=True))

        logger.info(f"Yelp hot_and_new: found {len(results)} restaurants")

    except httpx.HTTPStatusError as e:
        logger.error(f"Yelp API error: {e.response.status_code} {e.response.text}")
    except Exception as e:
        logger.error(f"Yelp collection failed: {e}")

    return results


async def collect_trending_by_category(client: httpx.AsyncClient) -> list[dict]:
    """
    Scan top categories sorted by review_count to detect review velocity.
    We compare current review counts against stored historical counts.
    """
    results = []

    for category in CUISINE_CATEGORIES:
        try:
            params = {
                "location": settings.yelp.location,
                "radius": settings.yelp.radius,
                "categories": category,
                "limit": 20,
                "sort_by": "review_count",
            }
            resp = await client.get(YELP_SEARCH_URL, headers=HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()

            for biz in data.get("businesses", []):
                results.append(_parse_business(biz, is_hot_and_new=False))

        except httpx.HTTPStatusError as e:
            logger.warning(f"Yelp category '{category}' error: {e.response.status_code}")
        except Exception as e:
            logger.warning(f"Yelp category '{category}' failed: {e}")

    logger.info(f"Yelp category scan: found {len(results)} restaurants across {len(CUISINE_CATEGORIES)} categories")
    return results


async def collect_recent_reviews(client: httpx.AsyncClient, yelp_id: str) -> list[dict]:
    """Fetch recent reviews for a specific restaurant to track sentiment."""
    reviews = []

    try:
        url = YELP_REVIEWS_URL.format(biz_id=yelp_id)
        resp = await client.get(url, headers=HEADERS, params={"limit": 20, "sort_by": "newest"})
        resp.raise_for_status()
        data = resp.json()

        for review in data.get("reviews", []):
            reviews.append({
                "source_id": review.get("id"),
                "source_url": review.get("url"),
                "content_snippet": review.get("text", "")[:500],
                "sentiment_score": analyze_sentiment(review.get("text", "")),
                "engagement": {"rating": review.get("rating", 0)},
                "time": review.get("time_created"),
            })

    except Exception as e:
        logger.warning(f"Failed to fetch reviews for {yelp_id}: {e}")

    return reviews


async def run(client: httpx.AsyncClient = None) -> dict:
    """
    Main entry point for Yelp collection.
    Returns summary stats.
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30)

    try:
        stats = {"hot_and_new": 0, "category_scan": 0, "mentions_created": 0}

        # Collect hot_and_new restaurants
        hot_new = await collect_hot_and_new(client)
        stats["hot_and_new"] = len(hot_new)

        # Collect by category for review velocity tracking
        by_category = await collect_trending_by_category(client)
        stats["category_scan"] = len(by_category)

        # Deduplicate and persist
        seen_ids = set()
        all_restaurants = hot_new + by_category

        for biz in all_restaurants:
            if biz["yelp_id"] in seen_ids:
                continue
            seen_ids.add(biz["yelp_id"])

            # Upsert restaurant record
            restaurant_id = upsert_restaurant(
                name=biz["name"],
                slug=biz["slug"],
                neighborhood=biz.get("neighborhood"),
                cuisine_type=biz.get("cuisine_type"),
                price_range=biz.get("price_range"),
                latitude=biz.get("latitude"),
                longitude=biz.get("longitude"),
                yelp_id=biz["yelp_id"],
                yelp_url=biz.get("yelp_url"),
                image_url=biz.get("image_url"),
            )

            # Create mention record
            insert_mention(
                restaurant_id=restaurant_id,
                platform="yelp",
                source_id=biz["yelp_id"],
                source_url=biz.get("yelp_url"),
                engagement={
                    "review_count": biz.get("review_count", 0),
                    "rating": biz.get("rating", 0),
                    "is_hot_and_new": biz.get("is_hot_and_new", False),
                },
                metadata={
                    "categories": biz.get("categories", []),
                    "price": biz.get("price_range"),
                },
            )
            stats["mentions_created"] += 1

        logger.info(f"Yelp collection complete: {stats}")
        return stats

    finally:
        if own_client:
            await client.aclose()


def _parse_business(biz: dict, is_hot_and_new: bool) -> dict:
    """Parse a Yelp business object into our standard format."""
    categories = [c["title"] for c in biz.get("categories", [])]
    location = biz.get("location", {})

    # Try to determine neighborhood
    neighborhood = None
    neighborhoods = location.get("address2") or location.get("address3")
    if not neighborhood:
        # Yelp sometimes puts neighborhood in the display_address
        display = location.get("display_address", [])
        if len(display) >= 2:
            neighborhood = display[0] if "," not in display[0] else None

    return {
        "name": biz["name"],
        "slug": generate_slug(biz["name"]),
        "yelp_id": biz["id"],
        "neighborhood": neighborhood,
        "cuisine_type": categories[0] if categories else None,
        "categories": categories,
        "price_range": biz.get("price"),
        "rating": biz.get("rating"),
        "review_count": biz.get("review_count", 0),
        "latitude": biz.get("coordinates", {}).get("latitude"),
        "longitude": biz.get("coordinates", {}).get("longitude"),
        "yelp_url": biz.get("url"),
        "image_url": biz.get("image_url"),
        "is_hot_and_new": is_hot_and_new,
    }
