"""
Google Trends collector.

Tracks search interest for known restaurant names in the SF metro area.
Uses pytrends (unofficial) for MVP; upgrade to SerpApi or official
Google Trends API for production reliability.

This is a supplementary signal (10% weight) that confirms whether
social media buzz is translating into actual search demand.
"""

import logging
import time
from datetime import datetime, timezone

from pytrends.request import TrendReq

from config import settings
from pipeline.utils.db import get_cursor, insert_mention

logger = logging.getLogger(__name__)

# Google Trends geo code for San Francisco Bay Area
SF_GEO = "US-CA-807"  # San Francisco-Oakland-San Jose DMA


def collect_trends_for_restaurants(restaurant_names: list[str]) -> dict:
    """
    Check Google Trends interest for a batch of restaurant names.

    pytrends allows up to 5 keywords per request.
    We batch accordingly and add delays to avoid rate limiting.
    """
    stats = {"restaurants_checked": 0, "trending_detected": 0}

    pytrends = TrendReq(hl="en-US", tz=480)  # Pacific time

    # Process in batches of 5
    for i in range(0, len(restaurant_names), 5):
        batch = restaurant_names[i : i + 5]

        try:
            pytrends.build_payload(
                kw_list=batch,
                cat=71,  # Food & Drink category
                timeframe="now 7-d",  # Last 7 days
                geo=SF_GEO,
            )

            # Interest over time
            interest = pytrends.interest_over_time()

            if interest.empty:
                continue

            for name in batch:
                if name not in interest.columns:
                    continue

                values = interest[name].tolist()
                if not values:
                    continue

                # Compute trend metrics
                recent_avg = sum(values[-3:]) / max(len(values[-3:]), 1)
                overall_avg = sum(values) / max(len(values), 1)
                peak = max(values)
                is_rising = recent_avg > overall_avg * 1.2  # 20%+ increase

                stats["restaurants_checked"] += 1
                if is_rising:
                    stats["trending_detected"] += 1

                yield {
                    "restaurant_name": name,
                    "interest_recent": recent_avg,
                    "interest_overall": overall_avg,
                    "interest_peak": peak,
                    "is_rising": is_rising,
                    "trend_ratio": (
                        recent_avg / overall_avg if overall_avg > 0 else 0
                    ),
                }

        except Exception as e:
            logger.warning(f"Google Trends batch failed: {e}")

        # Rate limiting: be gentle with the unofficial API
        time.sleep(2)

    logger.info(f"Google Trends collection: {stats}")


def run() -> dict:
    """Main entry point for Google Trends collection."""
    stats = {"restaurants_checked": 0, "mentions_created": 0}

    # Get top restaurants to check (limit to avoid rate limiting)
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, name FROM restaurants
            WHERE is_active = TRUE
            ORDER BY updated_at DESC
            LIMIT 50
        """)
        restaurants = {row["name"]: row["id"] for row in cur.fetchall()}

    names = list(restaurants.keys())

    for trend in collect_trends_for_restaurants(names):
        name = trend["restaurant_name"]
        restaurant_id = restaurants.get(name)

        if not restaurant_id:
            continue

        insert_mention(
            restaurant_id=restaurant_id,
            platform="trends",
            engagement={
                "interest_recent": trend["interest_recent"],
                "interest_overall": trend["interest_overall"],
                "interest_peak": trend["interest_peak"],
                "trend_ratio": trend["trend_ratio"],
            },
            metadata={
                "is_rising": trend["is_rising"],
                "geo": SF_GEO,
            },
        )
        stats["mentions_created"] += 1

    stats["restaurants_checked"] = len(names)
    logger.info(f"Google Trends complete: {stats}")
    return stats
