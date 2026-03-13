"""
Lightweight NLP utilities for sentiment analysis and restaurant name extraction.
Uses TextBlob for MVP; upgrade to spaCy or OpenAI for production.
"""

import re
import logging

from textblob import TextBlob

logger = logging.getLogger(__name__)

# Common SF restaurant name patterns to help extraction
NOISE_WORDS = {
    "restaurant", "cafe", "bar", "grill", "kitchen", "eatery",
    "bistro", "diner", "house", "place", "spot", "joint",
    "the", "a", "an", "at", "in", "on", "for", "of",
    "sf", "san francisco", "bay area", "oakland", "berkeley",
}


def analyze_sentiment(text: str) -> float:
    """
    Return sentiment polarity from -1.0 (negative) to 1.0 (positive).
    Uses TextBlob for MVP. Consider upgrading to:
      - OpenAI API for nuanced food-specific sentiment
      - Fine-tuned model on restaurant review data
    """
    if not text:
        return 0.0
    try:
        blob = TextBlob(text)
        return round(blob.sentiment.polarity, 3)
    except Exception as e:
        logger.warning(f"Sentiment analysis failed: {e}")
        return 0.0


def extract_restaurant_names(text: str, known_names: list[str] = None) -> list[str]:
    """
    Extract potential restaurant names from social media text.

    Strategy:
    1. Check against known restaurant names first (fast path)
    2. Look for common patterns: quoted names, capitalized sequences, @mentions
    3. Filter out noise words and common false positives

    Args:
        text: The post/comment text to analyze
        known_names: Optional list of known restaurant names to match against

    Returns:
        List of extracted restaurant name candidates
    """
    if not text:
        return []

    found = []

    # Strategy 1: Match known names (case-insensitive)
    if known_names:
        text_lower = text.lower()
        for name in known_names:
            if name.lower() in text_lower:
                found.append(name)

    # Strategy 2: Look for quoted restaurant names
    # People often write: went to "Burma Superstar" last night
    quoted = re.findall(r'["\u201c\u201d]([^"\u201c\u201d]{3,40})["\u201c\u201d]', text)
    for q in quoted:
        if q.lower() not in NOISE_WORDS and len(q.split()) <= 5:
            found.append(q.strip())

    # Strategy 3: Look for @mentions (Instagram/Threads style)
    mentions = re.findall(r"@(\w{3,30})", text)
    for m in mentions:
        # Filter out common non-restaurant mentions
        if not any(skip in m.lower() for skip in ["user", "admin", "mod", "bot"]):
            found.append(m)

    # Strategy 4: Look for "at [Name]" or "to [Name]" patterns
    at_patterns = re.findall(
        r"(?:at|to|tried|visited|went to|checked out)\s+([A-Z][A-Za-z\s'&]{2,30}?)(?:[.,!?\s]|$)",
        text,
    )
    for match in at_patterns:
        cleaned = match.strip().rstrip(".,!? ")
        if cleaned.lower() not in NOISE_WORDS and 2 <= len(cleaned.split()) <= 5:
            found.append(cleaned)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for name in found:
        normalized = name.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(name.strip())

    return unique


def is_food_related(text: str) -> bool:
    """Quick heuristic check if text is food/restaurant related."""
    food_signals = [
        "restaurant", "food", "eat", "dinner", "lunch", "brunch",
        "breakfast", "meal", "dish", "menu", "chef", "cook",
        "delicious", "tasty", "yummy", "reservation", "table",
        "order", "waitlist", "michelin", "yelp", "ramen",
        "sushi", "pizza", "taco", "burger", "pasta", "dim sum",
        "boba", "pho", "curry", "bbq", "seafood", "steak",
        "cocktail", "wine", "beer", "cafe", "bakery",
    ]
    text_lower = text.lower()
    return any(signal in text_lower for signal in food_signals)


def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a restaurant name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = slug.strip("-")
    return slug
