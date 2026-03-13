"""
Google Places API collector.

Tracks review count acceleration and rating changes for known restaurants.
Cannot detect trending natively, but review velocity over time is a strong signal.

Uses the Places API (New) with $200/month free credit.
Docs: https://developers.google.com/maps/documentation/places/web-service
"""

import logging
from datetime import datetime, timezone

import httpx

from config import settings
from pipeline.utils.db import get_cursor, insert_mention

logger = logging.getLogger(__name__)

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"


async def search_restaurant(client: httpx.AsyncClient, query: str) -> dict | None:
    """Search for a restaurant by name in the Bay Area."""
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.google_places.api_key,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,"
                "places.rating,places.userRatingCount,places.priceLevel,"
                "places.types,places.location,places.googleMapsUri,"
                "places.editorialSummary"
            ),
        }

        body = {
            "textQuery": f"{query} restaurant San Francisco Bay Area",
            "locationBias": {
                "circle": {
                    "center": {
                        "latitude": settings.geo.lat_center,
                        "longitude": settings.geo.lng_center,
                    },
                    "radius": settings.geo.radius_meters,
                }
            },
            "maxResultCount": 1,
        }

        resp = await client.post(PLACES_SEARCH_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

        places = data.get("places", [])
        if places:
            return places[0]

    except Exception as e:
        logger.warning(f"Google Places search for '{query}' failed: {e}")

    return None


async def enrich_known_restaurants(client: httpx.AsyncClient) -> dict:
    """
    For each known restaurant, fetch current Google Places data.
    The key signal is review_count delta over time.
    """
    stats = {"restaurants_checked": 0, "enriched": 0, "mentions_created": 0}

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, name, google_place_id
            FROM restaurants
            WHERE is_active = TRUE
            ORDER BY updated_at ASC
            LIMIT 100
        """)
        restaurants = cur.fetchall()

    for restaurant in restaurants:
        stats["restaurants_checked"] += 1

        try:
            if restaurant["google_place_id"]:
                # Direct lookup by place ID
                place = await _get_place_details(client, restaurant["google_place_id"])
            else:
                # Search by name
                place = await search_restaurant(client, restaurant["name"])

            if not place:
                continue

            # Extract signals
            review_count = place.get("userRatingCount", 0)
            rating = place.get("rating", 0)
            place_id = place.get("id", "")

            # Update restaurant with Google data if we found a new place_id
            if not restaurant["google_place_id"] and place_id:
                with get_cursor() as cur:
                    cur.execute("""
                        UPDATE restaurants
                        SET google_place_id = %s,
                            google_maps_url = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (
                        place_id,
                        place.get("googleMapsUri"),
                        restaurant["id"],
                    ))

            # Create mention with current review counts
            # The scoring engine computes velocity from historical snapshots
            insert_mention(
                restaurant_id=restaurant["id"],
                platform="google",
                source_id=place_id,
                source_url=place.get("googleMapsUri"),
                engagement={
                    "review_count": review_count,
                    "rating": rating,
                    "price_level": place.get("priceLevel"),
                },
                metadata={
                    "types": place.get("types", []),
                    "editorial_summary": (
                        place.get("editorialSummary", {}).get("text", "")
                    ),
                },
            )
            stats["enriched"] += 1
            stats["mentions_created"] += 1

        except Exception as e:
            logger.warning(f"Google Places enrichment for '{restaurant['name']}' failed: {e}")

    logger.info(f"Google Places enrichment complete: {stats}")
    return stats


async def _get_place_details(client: httpx.AsyncClient, place_id: str) -> dict | None:
    """Get details for a specific place by ID."""
    try:
        headers = {
            "X-Goog-Api-Key": settings.google_places.api_key,
            "X-Goog-FieldMask": (
                "id,displayName,formattedAddress,rating,userRatingCount,"
                "priceLevel,types,location,googleMapsUri,editorialSummary"
            ),
        }

        url = PLACE_DETAILS_URL.format(place_id=place_id)
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()

    except Exception as e:
        logger.warning(f"Google Place details for {place_id} failed: {e}")
        return None


async def run(client: httpx.AsyncClient = None) -> dict:
    """Main entry point for Google Places collection."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30)

    try:
        return await enrich_known_restaurants(client)
    finally:
        if own_client:
            await client.aclose()
