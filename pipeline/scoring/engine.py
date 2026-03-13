"""
Engagement Velocity Scoring Engine

The core algorithm that computes a composite trend score for each restaurant.
It measures HOW FAST a restaurant is gaining social attention, not just total attention.

The composite score combines five signals:
  1. Mention velocity (30%): Rate of new mentions vs. 30-day baseline
  2. Engagement acceleration (25%): Rate of change in engagement metrics
  3. Cross-platform spread (20%): Appearing on multiple platforms simultaneously
  4. Sentiment score (15%): Positive sentiment amplifies, negative suppresses
  5. Influencer signal (10%): High-reach accounts mentioning the restaurant

Each signal is z-score normalized against all restaurants in the scoring window
so that platform-specific metrics are comparable.

Data source: Google Sheets via gspread (replaces PostgreSQL).
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import numpy as np

from config import settings
from pipeline.utils.db import _get_worksheet, insert_trend_scores

logger = logging.getLogger(__name__)


@dataclass
class RestaurantSignals:
    """Raw signals for a single restaurant before normalization."""
    restaurant_id: int
    name: str

    # Mention velocity
    mentions_current: int = 0       # mentions in scoring window
    mentions_baseline: float = 0.0  # avg mentions per week over baseline period
    mention_velocity: float = 0.0   # current / baseline ratio

    # Engagement acceleration
    engagement_current: float = 0.0
    engagement_previous: float = 0.0
    engagement_acceleration: float = 0.0

    # Cross-platform spread
    platforms: set = None
    platform_count: int = 0

    # Sentiment
    avg_sentiment: float = 0.0

    # Influencer signal
    max_reach: int = 0
    high_reach_mentions: int = 0  # mentions from accounts with reach > threshold

    def __post_init__(self):
        if self.platforms is None:
            self.platforms = set()


def compute_scores() -> list[dict]:
    """
    Main scoring function. Reads Google Sheets for recent activity,
    computes raw signals, normalizes them, and produces ranked trend scores.
    """
    now = datetime.now(timezone.utc)
    scoring_window_start = now - timedelta(hours=settings.scoring.scoring_window_hours)
    baseline_start = now - timedelta(days=settings.scoring.baseline_days)

    # Step 1: Gather raw signals for all active restaurants
    signals = _gather_signals(scoring_window_start, baseline_start, now)

    if not signals:
        logger.warning("No signals found for any restaurant")
        return []

    # Step 2: Compute derived metrics
    for sig in signals.values():
        # Mention velocity: ratio of current to baseline
        if sig.mentions_baseline > 0:
            sig.mention_velocity = sig.mentions_current / sig.mentions_baseline
        elif sig.mentions_current > 0:
            sig.mention_velocity = sig.mentions_current * 2  # No baseline = bonus

        # Platform count
        sig.platform_count = len(sig.platforms)

    # Step 3: Z-score normalize each signal across all restaurants
    restaurant_list = list(signals.values())

    mention_velocities = np.array([s.mention_velocity for s in restaurant_list])
    engagement_accels = np.array([s.engagement_acceleration for s in restaurant_list])
    platform_counts = np.array([float(s.platform_count) for s in restaurant_list])
    sentiments = np.array([s.avg_sentiment for s in restaurant_list])
    influencer_signals = np.array([float(s.high_reach_mentions) for s in restaurant_list])

    mention_z = _zscore(mention_velocities)
    engagement_z = _zscore(engagement_accels)
    platform_z = _zscore(platform_counts)
    sentiment_z = _zscore(sentiments)
    influencer_z = _zscore(influencer_signals)

    # Step 4: Compute weighted composite score
    w = settings.scoring
    scores = []

    for i, sig in enumerate(restaurant_list):
        # Skip restaurants below minimum mention threshold
        if sig.mentions_current < w.min_mentions:
            continue

        composite = (
            mention_z[i] * w.mention_velocity_weight
            + engagement_z[i] * w.engagement_accel_weight
            + platform_z[i] * w.cross_platform_weight
            + sentiment_z[i] * w.sentiment_weight
            + influencer_z[i] * w.influencer_signal_weight
        )

        scores.append({
            "restaurant_id": sig.restaurant_id,
            "name": sig.name,
            "score": float(composite),
            "mention_velocity_score": float(mention_z[i]),
            "engagement_accel_score": float(engagement_z[i]),
            "cross_platform_score": float(platform_z[i]),
            "sentiment_score": float(sentiment_z[i]),
            "influencer_signal_score": float(influencer_z[i]),
            "platforms_active": list(sig.platforms),
            "raw": {
                "mentions_current": sig.mentions_current,
                "mentions_baseline": sig.mentions_baseline,
                "mention_velocity": sig.mention_velocity,
                "engagement_acceleration": sig.engagement_acceleration,
                "avg_sentiment": sig.avg_sentiment,
                "platform_count": sig.platform_count,
                "max_reach": sig.max_reach,
            },
        })

    # Step 5: Rank by composite score
    scores.sort(key=lambda x: x["score"], reverse=True)
    for rank, s in enumerate(scores, 1):
        s["rank"] = rank
        s["time"] = now

    logger.info(
        f"Scored {len(scores)} restaurants. "
        f"Top: {scores[0]['name'] if scores else 'N/A'} "
        f"(score: {scores[0]['score']:.2f})" if scores else ""
    )

    return scores


def run() -> dict:
    """Compute scores and persist to database."""
    scores = compute_scores()

    if scores:
        insert_trend_scores(scores)
        logger.info(f"Persisted {len(scores)} trend scores")

    return {
        "restaurants_scored": len(scores),
        "top_10": [
            {"rank": s["rank"], "name": s["name"], "score": round(s["score"], 2)}
            for s in scores[:10]
        ],
    }


# ============================================================
# Internal helpers
# ============================================================

def _parse_engagement(raw: str | dict) -> dict:
    """Parse engagement from a sheet cell (JSON string or already a dict)."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _total_engagement(engagement: dict) -> int:
    """Sum all engagement metrics from an engagement dict."""
    return sum([
        engagement.get("likes", 0) or 0,
        engagement.get("comments", 0) or 0,
        engagement.get("upvotes", 0) or 0,
        engagement.get("replies", 0) or 0,
        engagement.get("reposts", 0) or 0,
        engagement.get("shares", 0) or 0,
        engagement.get("plays", 0) or 0,
        engagement.get("score", 0) or 0,
    ])


def _parse_time(raw: str) -> datetime | None:
    """Parse a timestamp string from the sheet into a timezone-aware datetime."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        # Ensure timezone-aware (assume UTC if naive)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _safe_float(val, default: float = 0.0) -> float:
    """Safely convert a sheet cell value to float."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default: int = 0) -> int:
    """Safely convert a sheet cell value to int."""
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _gather_signals(
    window_start: datetime,
    baseline_start: datetime,
    now: datetime,
) -> dict[int, RestaurantSignals]:
    """Read Google Sheets and compute raw signals for each restaurant."""
    signals: dict[int, RestaurantSignals] = {}

    # ---- Load restaurants from sheet ----
    restaurants_ws = _get_worksheet("restaurants")
    all_restaurants = restaurants_ws.get_all_records()

    # Row-based IDs: row 2 = id 1, row 3 = id 2, etc.
    restaurant_names: dict[int, str] = {}
    for idx, r in enumerate(all_restaurants, 1):
        restaurant_names[idx] = r.get("name", f"Unknown #{idx}")

    # ---- Load mentions from sheet ----
    mentions_ws = _get_worksheet("mentions")
    all_mentions = mentions_ws.get_all_records()

    # ---- Classify each mention into scoring window or baseline window ----
    for m in all_mentions:
        mention_time = _parse_time(m.get("time", ""))
        if mention_time is None:
            continue

        restaurant_id = _safe_int(m.get("restaurant_id"))
        if restaurant_id == 0:
            continue

        platform = m.get("platform", "unknown")
        engagement = _parse_engagement(m.get("engagement", ""))
        sentiment = _safe_float(m.get("sentiment_score"))
        author_reach = _safe_int(m.get("author_reach"))

        eng_total = _total_engagement(engagement)

        # ---- Scoring window: window_start <= time <= now ----
        if mention_time >= window_start and mention_time <= now:
            # Initialize signal entry if new restaurant
            if restaurant_id not in signals:
                name = restaurant_names.get(
                    restaurant_id,
                    f"Unknown #{restaurant_id}",
                )
                signals[restaurant_id] = RestaurantSignals(
                    restaurant_id=restaurant_id,
                    name=name,
                )

            sig = signals[restaurant_id]
            sig.mentions_current += 1
            sig.platforms.add(platform)

            # Running average for sentiment
            sig.avg_sentiment = (sig.avg_sentiment + sentiment) / 2

            sig.engagement_current += eng_total
            sig.max_reach = max(sig.max_reach, author_reach)

            if author_reach > 10000:
                sig.high_reach_mentions += 1

        # ---- Baseline window: baseline_start <= time < window_start ----
        elif mention_time >= baseline_start and mention_time < window_start:
            # We need the restaurant in signals dict to record baseline.
            # If it only appears in baseline and not scoring window, we still
            # need it so the ratio can be computed, but it will be filtered out
            # later if mentions_current < min_mentions.
            if restaurant_id not in signals:
                name = restaurant_names.get(
                    restaurant_id,
                    f"Unknown #{restaurant_id}",
                )
                signals[restaurant_id] = RestaurantSignals(
                    restaurant_id=restaurant_id,
                    name=name,
                )

            sig = signals[restaurant_id]
            # Accumulate raw baseline counts (we'll normalize to weekly later)
            sig.mentions_baseline += 1
            sig.engagement_previous += eng_total

    # ---- Normalize baseline to weekly averages ----
    baseline_weeks = max((window_start - baseline_start).days / 7, 1)

    for sig in signals.values():
        sig.mentions_baseline = sig.mentions_baseline / baseline_weeks
        sig.engagement_previous = sig.engagement_previous / baseline_weeks

    # ---- Compute engagement acceleration ----
    for sig in signals.values():
        if sig.engagement_previous > 0:
            sig.engagement_acceleration = (
                (sig.engagement_current - sig.engagement_previous)
                / sig.engagement_previous
            )
        elif sig.engagement_current > 0:
            sig.engagement_acceleration = 1.0

    return signals


def _zscore(arr: np.ndarray) -> np.ndarray:
    """Compute z-scores, handling zero variance gracefully."""
    if len(arr) == 0:
        return arr
    mean = np.mean(arr)
    std = np.std(arr)
    if std == 0:
        return np.zeros_like(arr)
    return (arr - mean) / std
