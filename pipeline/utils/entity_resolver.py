"""
Entity resolution: extract restaurant names from social media captions.

This is the hardest part of the pipeline. A social media post might say:
  - "this place in the Mission is insane" (no name)
  - "Burma Superstar on Clement" (clear name)
  - "@burmasuperstar_sf best curry ever" (username is the restaurant)
  - "the birria tacos at this spot in the Sunset" (no name, but dish + neighborhood)

We use Claude to parse these captions and extract restaurant names with confidence
scores. Captions are batched to minimize API calls and cost.

Ported from Restaurant Finder's entity_resolver.py, adapted for the SF Trending
Eats pipeline: multi-platform input, Bay Area context, and integration with
the project's DB layer.
"""

import json
import logging
import os
from typing import Optional

from anthropic import Anthropic

from config import settings
from pipeline.utils.db import find_restaurant_by_name, insert_mention, upsert_restaurant
from pipeline.utils.nlp import analyze_sentiment, generate_slug

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — pull from settings.entity_resolver if it exists, else use defaults
# and fall back to ANTHROPIC_API_KEY env var / publishing config.
# ---------------------------------------------------------------------------

_er = getattr(settings, "entity_resolver", None)

ANTHROPIC_API_KEY = (
    getattr(_er, "api_key", None)
    or settings.publishing.anthropic_api_key
    or os.getenv("ANTHROPIC_API_KEY", "")
)
MODEL = getattr(_er, "model", None) or os.getenv(
    "ENTITY_RESOLVER_MODEL", "claude-sonnet-4-20250514"
)
BATCH_SIZE = getattr(_er, "batch_size", None) or int(
    os.getenv("ENTITY_RESOLVER_BATCH_SIZE", "20")
)
MIN_CONFIDENCE = getattr(_er, "min_confidence", None) or float(
    os.getenv("ENTITY_RESOLVER_MIN_CONFIDENCE", "0.5")
)

# Lazy-initialized Anthropic client
_client: Optional[Anthropic] = None


def _get_client() -> Anthropic:
    """Return a shared Anthropic client, creating it on first call."""
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "No Anthropic API key found. Set ANTHROPIC_API_KEY env var, "
                "settings.entity_resolver.api_key, or settings.publishing.anthropic_api_key."
            )
        _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are extracting restaurant names from social media posts about food in the San Francisco Bay Area.

For each post, return:
- restaurant_name: the name of the restaurant if you can identify it, or null if you cannot
- confidence: a number from 0.0 to 1.0 indicating how confident you are
- reasoning: one sentence explaining your extraction

Rules:
- If the post clearly names a restaurant, extract it (confidence 0.8 to 1.0)
- If an @ mention appears to be a restaurant account, extract the likely restaurant name from it (confidence 0.6 to 0.8)
- If a location_name is provided in the metadata, it is likely the restaurant name (confidence 0.9)
- If you recognize a known SF Bay Area restaurant, boost your confidence accordingly
- If the post mentions a specific dish + neighborhood but no restaurant name, return null (confidence 0.0)
- If the post is generic food content not about a specific restaurant, return null (confidence 0.0)
- Strip emojis, location pins, and formatting artifacts from restaurant names
- Return the commonly known name, not the full legal name

Respond ONLY with a JSON array, one object per post. No other text.

Posts:
{posts_json}
"""


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def extract_restaurants_batch(items: list[dict]) -> list[dict]:
    """
    Batch entity resolution via Claude API.

    Args:
        items: List of dicts, each with:
            - content_snippet: the caption / post text
            - source_id: the video/post ID (for tracking)
            - platform: "tiktok", "instagram", etc.
            - metadata: dict with optional hashtags, author_username, location_name

    Returns:
        List of dicts, each with:
            - source_id: from input
            - restaurant_name: extracted name or None
            - confidence: 0.0 to 1.0
            - reasoning: one sentence
    """
    if not items:
        return []

    # Build the posts payload for the prompt. Include metadata that helps
    # Claude resolve the entity (location tags, author handle, hashtags).
    posts_for_prompt = []
    for item in items:
        post = {
            "id": item["source_id"],
            "platform": item.get("platform", "unknown"),
            "caption": item.get("content_snippet", ""),
        }
        meta = item.get("metadata") or {}
        if meta.get("location_name"):
            post["location_tag"] = meta["location_name"]
        if meta.get("author_username"):
            post["author"] = meta["author_username"]
        if meta.get("hashtags"):
            post["hashtags"] = meta["hashtags"]
        posts_for_prompt.append(post)

    prompt_text = EXTRACTION_PROMPT.format(
        posts_json=json.dumps(posts_for_prompt, indent=2)
    )

    client = _get_client()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt_text}],
        )
        raw_text = response.content[0].text.strip()
    except Exception:
        logger.exception("Claude API call failed during entity extraction")
        # Return empty results so caller can decide how to handle
        return [
            {
                "source_id": item["source_id"],
                "restaurant_name": None,
                "confidence": 0.0,
                "reasoning": "API call failed",
            }
            for item in items
        ]

    # Parse the JSON response
    try:
        # Claude sometimes wraps JSON in markdown code fences
        cleaned = raw_text
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]  # drop first ``` line
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("Failed to parse Claude response as JSON: %s", raw_text[:500])
        return [
            {
                "source_id": item["source_id"],
                "restaurant_name": None,
                "confidence": 0.0,
                "reasoning": "Failed to parse API response",
            }
            for item in items
        ]

    # Map results back to source_ids, handling mismatches gracefully
    results = []
    for i, item in enumerate(items):
        if i < len(parsed):
            entry = parsed[i]
            results.append({
                "source_id": item["source_id"],
                "restaurant_name": entry.get("restaurant_name"),
                "confidence": float(entry.get("confidence", 0.0)),
                "reasoning": entry.get("reasoning", ""),
            })
        else:
            logger.warning(
                "Claude returned fewer results (%d) than inputs (%d); "
                "marking item %s as unresolved",
                len(parsed), len(items), item["source_id"],
            )
            results.append({
                "source_id": item["source_id"],
                "restaurant_name": None,
                "confidence": 0.0,
                "reasoning": "Missing from API response",
            })

    return results


# ---------------------------------------------------------------------------
# Full pipeline: resolve + persist
# ---------------------------------------------------------------------------


def resolve_and_persist(mentions: list[dict]) -> dict:
    """
    End-to-end entity resolution and database persistence.

    Takes unresolved mentions, extracts restaurant names via Claude, matches
    against existing DB entries, creates new restaurants as needed, and
    inserts mention records.

    Args:
        mentions: List of dicts, each with:
            - content_snippet: the caption / post text
            - source_id: the video/post ID
            - platform: "tiktok", "instagram", etc.
            - metadata: dict with optional hashtags, author_username, location_name
            (may also include: source_url, engagement, author_reach, time)

    Returns:
        Dict with stats:
            - total: number of mentions processed
            - resolved_count: mentions where a restaurant was identified
            - new_restaurants: restaurants created in the DB
            - matched_existing: mentions matched to an existing restaurant
            - skipped_low_confidence: mentions below min_confidence threshold
    """
    stats = {
        "total": len(mentions),
        "resolved_count": 0,
        "new_restaurants": 0,
        "matched_existing": 0,
        "skipped_low_confidence": 0,
    }

    if not mentions:
        return stats

    # Build a lookup from source_id -> original mention for later persistence
    mention_lookup = {m["source_id"]: m for m in mentions}

    # Process in batches
    all_results = []
    for batch_start in range(0, len(mentions), BATCH_SIZE):
        batch = mentions[batch_start : batch_start + BATCH_SIZE]
        logger.info(
            "Extracting restaurants from batch %d-%d of %d mentions",
            batch_start + 1,
            min(batch_start + BATCH_SIZE, len(mentions)),
            len(mentions),
        )
        batch_results = extract_restaurants_batch(batch)
        all_results.extend(batch_results)

    # Persist resolved mentions
    for result in all_results:
        source_id = result["source_id"]
        restaurant_name = result.get("restaurant_name")
        confidence = result.get("confidence", 0.0)

        if not restaurant_name or confidence < MIN_CONFIDENCE:
            stats["skipped_low_confidence"] += 1
            logger.debug(
                "Skipping %s: name=%s, confidence=%.2f (min=%.2f)",
                source_id, restaurant_name, confidence, MIN_CONFIDENCE,
            )
            continue

        stats["resolved_count"] += 1
        original = mention_lookup.get(source_id, {})

        # Check for existing restaurant in the database
        existing = find_restaurant_by_name(restaurant_name)

        if existing:
            restaurant_id = existing["id"]
            stats["matched_existing"] += 1
            logger.debug(
                "Matched '%s' to existing restaurant '%s' (id=%d, sim=%.2f)",
                restaurant_name, existing["name"], restaurant_id,
                existing.get("sim", 0),
            )
        else:
            # Create a new restaurant entry
            slug = generate_slug(restaurant_name)
            restaurant_id = upsert_restaurant(
                name=restaurant_name,
                slug=slug,
            )
            stats["new_restaurants"] += 1
            logger.info(
                "Created new restaurant '%s' (slug=%s, id=%d)",
                restaurant_name, slug, restaurant_id,
            )

        # Compute sentiment from the original caption
        content_snippet = original.get("content_snippet", "")
        sentiment = analyze_sentiment(content_snippet)

        # Build metadata for the mention record, including resolution info
        mention_metadata = original.get("metadata") or {}
        mention_metadata["entity_resolution"] = {
            "confidence": confidence,
            "reasoning": result.get("reasoning", ""),
            "resolved_name": restaurant_name,
        }

        # Insert the mention
        insert_mention(
            restaurant_id=restaurant_id,
            platform=original.get("platform", "unknown"),
            source_id=source_id,
            source_url=original.get("source_url"),
            content_snippet=content_snippet,
            engagement=original.get("engagement"),
            sentiment_score=sentiment,
            author_reach=original.get("author_reach", 0),
            metadata=mention_metadata,
            time=original.get("time"),
        )

    logger.info(
        "Entity resolution complete: %d total, %d resolved "
        "(%d new restaurants, %d matched existing), %d skipped",
        stats["total"],
        stats["resolved_count"],
        stats["new_restaurants"],
        stats["matched_existing"],
        stats["skipped_low_confidence"],
    )

    return stats


# ---------------------------------------------------------------------------
# CLI test harness
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    # Sample SF Bay Area social media posts for testing
    test_items = [
        {
            "source_id": "test_001",
            "platform": "tiktok",
            "content_snippet": "the birria tacos at this spot in the Mission are insane",
            "metadata": {"hashtags": ["#sffood", "#birriatacos"]},
        },
        {
            "source_id": "test_002",
            "platform": "instagram",
            "content_snippet": "Best dim sum in SF hands down",
            "metadata": {"location_name": "Dumpling Home", "author_username": "sffoodie"},
        },
        {
            "source_id": "test_003",
            "platform": "tiktok",
            "content_snippet": "Burma Superstar on Clement Street never disappoints",
            "metadata": {"hashtags": ["#burmasuperstar", "#sfeats"]},
        },
        {
            "source_id": "test_004",
            "platform": "instagram",
            "content_snippet": "@tartinebakery croissants are the best in the city",
            "metadata": {"author_username": "bayareabites"},
        },
        {
            "source_id": "test_005",
            "platform": "reddit",
            "content_snippet": "Just tried Che Fico on Divisadero and wow, the pasta is incredible",
            "metadata": {},
        },
        {
            "source_id": "test_006",
            "platform": "threads",
            "content_snippet": "generic food pic with no restaurant info at all lol",
            "metadata": {},
        },
    ]

    print(f"\nExtracting restaurants from {len(test_items)} test posts...\n")
    results = extract_restaurants_batch(test_items)

    for r in results:
        name = r["restaurant_name"] or "(none)"
        print(f"  [{r['source_id']}] {name} (confidence: {r['confidence']:.2f})")
        print(f"    Reasoning: {r['reasoning']}")
    print()
