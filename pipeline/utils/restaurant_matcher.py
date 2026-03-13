"""
Restaurant name matching and deduplication across data sources.

The same restaurant may appear as:
  - "Burma Superstar" (Yelp)
  - "burma_superstar_sf" (Instagram)
  - "Burma Superstar on Clement" (Reddit)
  - "Burma Super Star" (Google)

This module handles fuzzy matching to resolve these to a single entity.
"""

import re
import logging
from difflib import SequenceMatcher

from pipeline.utils.nlp import generate_slug

logger = logging.getLogger(__name__)

# Words to strip when comparing restaurant names
STRIP_WORDS = {
    "the", "a", "an", "restaurant", "cafe", "bar", "grill",
    "kitchen", "eatery", "bistro", "sf", "san francisco",
    "oakland", "berkeley", "bay area",
}


def normalize_name(name: str) -> str:
    """Normalize a restaurant name for comparison."""
    normalized = name.lower().strip()
    # Remove common suffixes/prefixes
    for word in STRIP_WORDS:
        normalized = re.sub(rf"\b{word}\b", "", normalized)
    # Remove special characters
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def name_similarity(name1: str, name2: str) -> float:
    """
    Compute similarity between two restaurant names.
    Returns 0.0 to 1.0.
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return 0.0

    # Exact match after normalization
    if n1 == n2:
        return 1.0

    # One contains the other
    if n1 in n2 or n2 in n1:
        return 0.9

    # Sequence matching
    return SequenceMatcher(None, n1, n2).ratio()


def find_best_match(
    candidate_name: str,
    known_restaurants: list[dict],
    threshold: float = 0.75,
) -> dict | None:
    """
    Find the best matching restaurant from a list of known restaurants.

    Args:
        candidate_name: The name to match
        known_restaurants: List of dicts with at least a 'name' key
        threshold: Minimum similarity score to consider a match

    Returns:
        Best matching restaurant dict, or None if no match above threshold
    """
    if not candidate_name or not known_restaurants:
        return None

    best_match = None
    best_score = 0.0

    for restaurant in known_restaurants:
        score = name_similarity(candidate_name, restaurant["name"])
        if score > best_score:
            best_score = score
            best_match = restaurant

    if best_score >= threshold:
        logger.debug(
            f"Matched '{candidate_name}' to '{best_match['name']}' "
            f"(score: {best_score:.2f})"
        )
        return best_match

    return None


def deduplicate_mentions(mentions: list[dict]) -> list[dict]:
    """
    Group mentions that refer to the same restaurant.
    Uses the restaurant_id if already resolved, otherwise fuzzy matches names.
    """
    # Group by restaurant_id where available
    by_id = {}
    unresolved = []

    for mention in mentions:
        rid = mention.get("restaurant_id")
        if rid:
            by_id.setdefault(rid, []).append(mention)
        else:
            unresolved.append(mention)

    # Try to resolve unresolved mentions against known ones
    known_names = []
    for rid, group in by_id.items():
        if group:
            known_names.append({
                "restaurant_id": rid,
                "name": group[0].get("restaurant_name", ""),
            })

    for mention in unresolved:
        name = mention.get("restaurant_name", "")
        match = find_best_match(name, known_names)
        if match:
            mention["restaurant_id"] = match["restaurant_id"]
            by_id.setdefault(match["restaurant_id"], []).append(mention)
        else:
            # New restaurant, create a temporary group
            temp_id = f"new_{generate_slug(name)}"
            mention["restaurant_id"] = temp_id
            by_id.setdefault(temp_id, []).append(mention)
            known_names.append({
                "restaurant_id": temp_id,
                "name": name,
            })

    # Flatten back to list
    result = []
    for group in by_id.values():
        result.extend(group)

    return result
