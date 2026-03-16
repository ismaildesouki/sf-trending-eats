"""
Instagram multi-strategy collector via Apify.

Collects Instagram posts through three complementary strategies:

  1. **Hashtag search** -- apify/instagram-hashtag-scraper actor, driven by
     settings.instagram.hashtags.
  2. **Place search** -- apify/instagram-scraper actor with searchType="place"
     for "San Francisco", returning geo-tagged posts.
  3. **Influencer profiles** -- apify/instagram-scraper actor scraping known
     SF food influencer profiles (settings.instagram.influencer_profiles).

Posts from all strategies are deduplicated by post ID, then fed into the
same restaurant extraction logic (location tags + caption NLP).

Apify free tier runs are billed per compute unit (~$5-15/mo at our volume).
Docs:
  - https://apify.com/apify/instagram-hashtag-scraper
  - https://apify.com/apify/instagram-scraper
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
from pipeline.utils.db import upsert_restaurant, insert_mention, get_all_restaurant_names

logger = logging.getLogger(__name__)

# Strategy 1 uses the dedicated hashtag scraper actor
HASHTAG_ACTOR_ID = "apify/instagram-hashtag-scraper"

# Strategies 2 & 3 use the full Instagram scraper actor
SCRAPER_ACTOR_ID = "apify/instagram-scraper"


# ---------------------------------------------------------------------------
# Existing helper functions (unchanged)
# ---------------------------------------------------------------------------

def _get_known_restaurant_names() -> list[str]:
    """Load known restaurant names from the sheet for matching."""
    try:
        return get_all_restaurant_names()
    except Exception as e:
        logger.warning(f"Could not load known restaurant names: {e}")
        return []


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


# ---------------------------------------------------------------------------
# Strategy 1: Hashtag search
# ---------------------------------------------------------------------------

def _scrape_hashtags(apify_client: ApifyClient) -> list[dict]:
    """
    Run the Apify Instagram hashtag scraper for all configured hashtags.

    Uses the ``apify/instagram-hashtag-scraper`` actor.
    Returns a flat list of raw post items (may contain duplicates across
    hashtags -- dedup happens in the main ``run()`` function).
    """
    hashtags = settings.instagram.hashtags
    limit = settings.instagram.results_per_hashtag
    all_items: list[dict] = []

    for hashtag in hashtags:
        run_input = {
            "hashtags": [hashtag],
            "resultsType": "posts",
            "resultsLimit": limit,
        }

        logger.info(f"Instagram [hashtag]: scraping #{hashtag} (limit={limit})")

        try:
            run = apify_client.actor(HASHTAG_ACTOR_ID).call(run_input=run_input)
            items = list(
                apify_client.dataset(run["defaultDatasetId"]).iterate_items()
            )
            logger.info(f"Instagram [hashtag]: #{hashtag} returned {len(items)} posts")
            all_items.extend(items)
        except Exception as e:
            logger.error(f"Instagram [hashtag]: Apify scrape failed for #{hashtag}: {e}")

    return all_items


# ---------------------------------------------------------------------------
# Strategy 2: Place search
# ---------------------------------------------------------------------------

def _scrape_places(apify_client: ApifyClient) -> list[dict]:
    """
    Search Instagram for posts tagged at places matching "San Francisco".

    Uses the ``apify/instagram-scraper`` actor with ``searchType="place"``.
    Returns a flat list of raw post items.
    """
    run_input = {
        "search": "San Francisco",
        "searchType": "place",
        "resultsType": "posts",
        "resultsLimit": 200,
        "onlyPostsNewerThan": "30 days",
    }

    logger.info("Instagram [place]: scraping place search for 'San Francisco' (limit=200)")

    try:
        run = apify_client.actor(SCRAPER_ACTOR_ID).call(run_input=run_input)
        items = list(
            apify_client.dataset(run["defaultDatasetId"]).iterate_items()
        )
        logger.info(f"Instagram [place]: place search returned {len(items)} posts")
        return items
    except Exception as e:
        logger.error(f"Instagram [place]: Apify place scrape failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Strategy 3: SF food influencer profiles
# ---------------------------------------------------------------------------

def _scrape_influencers(apify_client: ApifyClient) -> list[dict]:
    """
    Scrape recent posts from known SF food influencer profiles.

    Uses the ``apify/instagram-scraper`` actor with ``directUrls`` pointing
    at each influencer profile. Only returns posts from the last 30 days,
    up to 30 posts per profile.
    """
    profiles = settings.instagram.influencer_profiles
    if not profiles:
        logger.info("Instagram [influencer]: no influencer profiles configured, skipping")
        return []

    run_input = {
        "directUrls": profiles,
        "resultsType": "posts",
        "resultsLimit": 30,
        "onlyPostsNewerThan": "30 days",
    }

    logger.info(
        f"Instagram [influencer]: scraping {len(profiles)} influencer profiles "
        f"(limit=30 posts each, last 30 days)"
    )

    try:
        run = apify_client.actor(SCRAPER_ACTOR_ID).call(run_input=run_input)
        items = list(
            apify_client.dataset(run["defaultDatasetId"]).iterate_items()
        )
        logger.info(f"Instagram [influencer]: returned {len(items)} posts total")
        return items
    except Exception as e:
        logger.error(f"Instagram [influencer]: Apify influencer scrape failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Shared post-processing & persistence
# ---------------------------------------------------------------------------

def _process_items(
    items: list[dict],
    strategy: str,
    seen_ids: set[str],
    known_names: list[str],
    stats: dict,
) -> None:
    """
    Process raw Instagram post items: extract restaurant names, persist
    mentions, and update *stats* in place.

    *strategy* is one of ``"hashtag"``, ``"place"``, or ``"influencer"``
    and is recorded in both the stats breakdown and each mention's metadata.

    Posts whose ID is already in *seen_ids* are silently skipped
    (cross-strategy dedup).
    """
    strategy_key = f"posts_from_{strategy}"
    if strategy_key not in stats:
        stats[strategy_key] = 0

    for item in items:
        post_id = item.get("id")
        if not post_id or post_id in seen_ids:
            continue
        seen_ids.add(post_id)

        stats["posts_collected"] += 1
        stats[strategy_key] += 1

        caption = item.get("caption") or ""
        location_name = item.get("locationName")

        # --- Identify restaurant names ---
        # Two signals: location tag (high confidence) and caption NLP.

        restaurant_names: list[str] = []
        name_sources: dict[str, str] = {}  # name -> source

        # Signal 1: Location tag -- essentially a confirmed mention.
        if location_name:
            restaurant_names.append(location_name)
            name_sources[location_name.lower()] = "location_tag"

        # Signal 2: Extract names from caption text via NLP.
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
                        "collection_strategy": strategy,
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


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run(client: httpx.AsyncClient = None) -> dict:
    """
    Main entry point for Instagram collection.

    Executes three collection strategies in sequence, deduplicates posts
    across strategies by post ID, extracts restaurant names from captions
    and location tags, then upserts restaurants and inserts mentions.

    Returns summary stats dict with per-strategy breakdowns.
    """
    stats = {
        "posts_collected": 0,
        "restaurants_matched": 0,
        "from_location_tag": 0,
        "from_caption": 0,
        "posts_from_hashtag": 0,
        "posts_from_place": 0,
        "posts_from_influencer": 0,
    }

    if not settings.instagram.apify_token:
        logger.warning("Instagram: APIFY_TOKEN not set, skipping collection")
        return stats

    apify_client = ApifyClient(settings.instagram.apify_token)
    known_names = _get_known_restaurant_names()
    seen_ids: set[str] = set()

    # --- Strategy 1: Hashtag search ---
    try:
        logger.info("Instagram: starting Strategy 1 — hashtag search")
        hashtag_items = _scrape_hashtags(apify_client)
        _process_items(hashtag_items, "hashtag", seen_ids, known_names, stats)
        logger.info(
            f"Instagram: Strategy 1 complete — "
            f"{stats['posts_from_hashtag']} unique posts from hashtags"
        )
    except Exception as e:
        logger.error(f"Instagram: Strategy 1 (hashtag) failed entirely: {e}")

    # --- Strategy 2: Place search ---
    try:
        logger.info("Instagram: starting Strategy 2 — place search")
        place_items = _scrape_places(apify_client)
        _process_items(place_items, "place", seen_ids, known_names, stats)
        logger.info(
            f"Instagram: Strategy 2 complete — "
            f"{stats['posts_from_place']} unique posts from place search"
        )
    except Exception as e:
        logger.error(f"Instagram: Strategy 2 (place) failed entirely: {e}")

    # --- Strategy 3: Influencer profiles ---
    try:
        logger.info("Instagram: starting Strategy 3 — influencer profiles")
        influencer_items = _scrape_influencers(apify_client)
        _process_items(influencer_items, "influencer", seen_ids, known_names, stats)
        logger.info(
            f"Instagram: Strategy 3 complete — "
            f"{stats['posts_from_influencer']} unique posts from influencers"
        )
    except Exception as e:
        logger.error(f"Instagram: Strategy 3 (influencer) failed entirely: {e}")

    logger.info(f"Instagram collection complete: {stats}")
    return stats
