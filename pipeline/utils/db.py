"""
Database helper functions backed by Google Sheets.
Uses gspread with service-account auth.
"""

import json
import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher

import gspread

from config import settings

logger = logging.getLogger(__name__)

# ---- module-level cache ------------------------------------------------
_client: gspread.Client | None = None
_spreadsheet: gspread.Spreadsheet | None = None
_worksheets: dict[str, gspread.Worksheet] = {}

# Column orderings for each sheet (must match header rows)
_RESTAURANT_COLS = [
    "id", "name", "slug", "neighborhood", "cuisine_type", "price_range",
    "latitude", "longitude", "yelp_id", "google_place_id", "yelp_url",
    "google_maps_url", "image_url", "first_seen", "updated_at",
]

_MENTION_COLS = [
    "time", "restaurant_id", "platform", "source_id", "source_url",
    "content_snippet", "engagement", "sentiment_score", "author_reach",
    "metadata",
]

_SCORE_COLS = [
    "time", "restaurant_id", "name", "score", "rank",
    "mention_velocity_score", "engagement_accel_score",
    "cross_platform_score", "sentiment_score", "influencer_signal_score",
    "platforms_active", "trending_reason", "metadata",
]

_WEEKLY_LIST_COLS = [
    "id", "week_start", "published_at", "status", "restaurant_ids",
    "newsletter_url",
]


# ============================================================
# Connection / setup
# ============================================================

def get_sheet() -> gspread.Spreadsheet:
    """Get the gspread spreadsheet object (cached)."""
    global _client, _spreadsheet
    if _spreadsheet is None:
        creds_file = getattr(settings.db, "credentials_file", "credentials.json")
        _client = gspread.service_account(filename=creds_file)
        _spreadsheet = _client.open_by_key(settings.db.spreadsheet_id)
        logger.info("Connected to Google Sheet: %s", settings.db.spreadsheet_id)
    return _spreadsheet


def _get_worksheet(name: str) -> gspread.Worksheet:
    """Get a specific worksheet by name (cached)."""
    if name not in _worksheets:
        sheet = get_sheet()
        _worksheets[name] = sheet.worksheet(name)
    return _worksheets[name]


# ---- helpers -----------------------------------------------------------

def _row_to_dict(row: list, columns: list[str]) -> dict:
    """Convert a sheet row (list of cell values) into a dict."""
    d = {}
    for i, col in enumerate(columns):
        val = row[i] if i < len(row) else ""
        d[col] = val
    return d


def _parse_json_field(value: str):
    """Safely parse a JSON-encoded cell value."""
    if not value:
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_str(value) -> str:
    """Convert a value to a string suitable for a Google Sheets cell."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


# ============================================================
# Restaurant CRUD
# ============================================================

def upsert_restaurant(
    name: str,
    slug: str,
    neighborhood: str = None,
    cuisine_type: str = None,
    price_range: str = None,
    latitude: float = None,
    longitude: float = None,
    yelp_id: str = None,
    google_place_id: str = None,
    yelp_url: str = None,
    google_maps_url: str = None,
    image_url: str = None,
) -> int:
    """Insert or update a restaurant. Match by slug. Return row-based id."""
    try:
        ws = _get_worksheet("restaurants")
        all_rows = ws.get_all_values()  # includes header

        # Search for existing slug (column index 2 = slug)
        existing_row_idx = None
        for i, row in enumerate(all_rows):
            if i == 0:
                continue  # skip header
            if len(row) > 2 and row[2] == slug:
                existing_row_idx = i + 1  # gspread is 1-indexed
                break

        now = _now_iso()

        if existing_row_idx is not None:
            # Update: COALESCE-like logic — only overwrite if new value is not None
            existing = all_rows[existing_row_idx - 1]
            existing_dict = _row_to_dict(existing, _RESTAURANT_COLS)

            def _coalesce(new_val, col_name):
                return _to_str(new_val) if new_val is not None else existing_dict.get(col_name, "")

            updated_row = [
                existing_dict.get("id", str(existing_row_idx - 1)),  # keep existing id
                _coalesce(name, "name"),
                slug,
                _coalesce(neighborhood, "neighborhood"),
                _coalesce(cuisine_type, "cuisine_type"),
                _coalesce(price_range, "price_range"),
                _coalesce(latitude, "latitude"),
                _coalesce(longitude, "longitude"),
                _coalesce(yelp_id, "yelp_id"),
                _coalesce(google_place_id, "google_place_id"),
                _coalesce(yelp_url, "yelp_url"),
                _coalesce(google_maps_url, "google_maps_url"),
                _coalesce(image_url, "image_url"),
                existing_dict.get("first_seen", now),
                now,  # updated_at
            ]
            ws.update(f"A{existing_row_idx}:{chr(64 + len(_RESTAURANT_COLS))}{existing_row_idx}", [updated_row])
            restaurant_id = existing_row_idx - 1  # row 2 = id 1
            logger.debug("Updated restaurant '%s' (id=%d)", name, restaurant_id)
            return restaurant_id
        else:
            # Insert new row
            new_id = len(all_rows)  # next row number minus header = id
            new_row = [
                str(new_id),
                _to_str(name),
                _to_str(slug),
                _to_str(neighborhood),
                _to_str(cuisine_type),
                _to_str(price_range),
                _to_str(latitude),
                _to_str(longitude),
                _to_str(yelp_id),
                _to_str(google_place_id),
                _to_str(yelp_url),
                _to_str(google_maps_url),
                _to_str(image_url),
                now,  # first_seen
                now,  # updated_at
            ]
            ws.append_row(new_row, value_input_option="RAW")
            logger.debug("Inserted restaurant '%s' (id=%d)", name, new_id)
            return new_id
    except Exception:
        logger.exception("Error upserting restaurant '%s'", name)
        raise


def find_restaurant_by_name(name: str) -> dict | None:
    """Fuzzy match using difflib.SequenceMatcher (threshold 0.3)."""
    try:
        ws = _get_worksheet("restaurants")
        all_rows = ws.get_all_values()

        best_match = None
        best_score = 0.0

        for i, row in enumerate(all_rows):
            if i == 0:
                continue
            if len(row) < 2:
                continue
            row_name = row[1]  # name is column index 1
            sim = SequenceMatcher(None, name.lower(), row_name.lower()).ratio()
            if sim > 0.3 and sim > best_score:
                best_score = sim
                best_match = _row_to_dict(row, _RESTAURANT_COLS)
                best_match["sim"] = sim

        return best_match
    except Exception:
        logger.exception("Error finding restaurant by name '%s'", name)
        return None


def get_restaurant_by_slug(slug: str) -> dict | None:
    """Find restaurant by exact slug match."""
    try:
        ws = _get_worksheet("restaurants")
        all_rows = ws.get_all_values()

        for i, row in enumerate(all_rows):
            if i == 0:
                continue
            if len(row) > 2 and row[2] == slug:
                return _row_to_dict(row, _RESTAURANT_COLS)
        return None
    except Exception:
        logger.exception("Error getting restaurant by slug '%s'", slug)
        return None


# ============================================================
# Mentions
# ============================================================

def insert_mention(
    restaurant_id: int,
    platform: str,
    source_id: str = None,
    source_url: str = None,
    content_snippet: str = None,
    engagement: dict = None,
    sentiment_score: float = None,
    author_reach: int = 0,
    metadata: dict = None,
    time: datetime = None,
):
    """Append a mention row."""
    try:
        ws = _get_worksheet("mentions")
        ts = time or datetime.now(timezone.utc)
        row = [
            _to_str(ts),
            str(restaurant_id),
            _to_str(platform),
            _to_str(source_id),
            _to_str(source_url),
            _to_str((content_snippet or "")[:500]),
            json.dumps(engagement or {}),
            _to_str(sentiment_score),
            str(author_reach),
            json.dumps(metadata or {}),
        ]
        ws.append_row(row, value_input_option="RAW")
        logger.debug("Inserted mention for restaurant_id=%d on %s", restaurant_id, platform)
    except Exception:
        logger.exception("Error inserting mention for restaurant_id=%d", restaurant_id)
        raise


def insert_mention_batch(mentions: list[dict]):
    """Bulk append mentions (uses batch append_rows for efficiency)."""
    if not mentions:
        return
    try:
        ws = _get_worksheet("mentions")
        rows = []
        for m in mentions:
            ts = m.get("time", datetime.now(timezone.utc))
            rows.append([
                _to_str(ts),
                str(m["restaurant_id"]),
                _to_str(m.get("platform", "")),
                _to_str(m.get("source_id")),
                _to_str(m.get("source_url")),
                _to_str((m.get("content_snippet") or "")[:500]),
                json.dumps(m.get("engagement", {})),
                _to_str(m.get("sentiment_score")),
                str(m.get("author_reach", 0)),
                json.dumps(m.get("metadata", {})),
            ])
        ws.append_rows(rows, value_input_option="RAW")
        logger.info("Batch-inserted %d mentions", len(rows))
    except Exception:
        logger.exception("Error batch-inserting %d mentions", len(mentions))
        raise


# ============================================================
# Trend Scores
# ============================================================

def insert_trend_scores(scores: list[dict]):
    """Append computed trend scores."""
    if not scores:
        return
    try:
        ws = _get_worksheet("scores")
        rows = []
        for s in scores:
            ts = s.get("time", datetime.now(timezone.utc))
            rows.append([
                _to_str(ts),
                str(s["restaurant_id"]),
                _to_str(s.get("name", "")),
                _to_str(s["score"]),
                _to_str(s.get("rank", "")),
                _to_str(s.get("mention_velocity_score", 0)),
                _to_str(s.get("engagement_accel_score", 0)),
                _to_str(s.get("cross_platform_score", 0)),
                _to_str(s.get("sentiment_score", 0)),
                _to_str(s.get("influencer_signal_score", 0)),
                json.dumps(s.get("platforms_active", [])),
                _to_str(s.get("trending_reason", "")),
                json.dumps(s.get("metadata", {})),
            ])
        ws.append_rows(rows, value_input_option="RAW")
        logger.info("Inserted %d trend scores", len(rows))
    except Exception:
        logger.exception("Error inserting %d trend scores", len(scores))
        raise


def get_latest_trending(n: int = 10) -> list[dict]:
    """Get the most recent top N trending restaurants by score."""
    try:
        ws = _get_worksheet("scores")
        all_rows = ws.get_all_values()

        if len(all_rows) <= 1:
            return []

        # Parse all score rows
        entries = []
        for i, row in enumerate(all_rows):
            if i == 0:
                continue
            d = _row_to_dict(row, _SCORE_COLS)
            # Parse numeric score for sorting
            try:
                d["score"] = float(d["score"])
            except (ValueError, TypeError):
                d["score"] = 0.0
            # Parse JSON fields
            d["platforms_active"] = _parse_json_field(d.get("platforms_active", ""))
            d["metadata"] = _parse_json_field(d.get("metadata", ""))
            entries.append(d)

        # Find the most recent timestamp to identify the latest scoring run
        if not entries:
            return []

        entries.sort(key=lambda x: x.get("time", ""), reverse=True)
        latest_time = entries[0].get("time", "")

        # Get all entries from the latest scoring run
        latest_entries = [e for e in entries if e.get("time", "") == latest_time]

        # Sort by score descending, return top N
        latest_entries.sort(key=lambda x: x["score"], reverse=True)
        return latest_entries[:n]
    except Exception:
        logger.exception("Error getting latest trending")
        return []


# ============================================================
# Weekly Lists
# ============================================================

def create_weekly_list(week_start, restaurant_ids: list[int]) -> int:
    """Create or update a weekly list entry. Returns row-based id."""
    try:
        ws = _get_worksheet("weekly_lists")
        all_rows = ws.get_all_values()

        week_start_str = _to_str(week_start)

        # Check if a row with this week_start already exists (column index 1)
        existing_row_idx = None
        for i, row in enumerate(all_rows):
            if i == 0:
                continue
            if len(row) > 1 and row[1] == week_start_str:
                existing_row_idx = i + 1  # gspread 1-indexed
                break

        now = _now_iso()

        if existing_row_idx is not None:
            list_id = existing_row_idx - 1
            updated_row = [
                str(list_id),
                week_start_str,
                "",  # published_at cleared on re-draft
                "draft",
                json.dumps(restaurant_ids),
                "",  # newsletter_url cleared
            ]
            ws.update(
                f"A{existing_row_idx}:{chr(64 + len(_WEEKLY_LIST_COLS))}{existing_row_idx}",
                [updated_row],
            )
            logger.debug("Updated weekly list id=%d for week %s", list_id, week_start_str)
            return list_id
        else:
            new_id = len(all_rows)  # row count minus header
            new_row = [
                str(new_id),
                week_start_str,
                "",  # published_at
                "draft",
                json.dumps(restaurant_ids),
                "",  # newsletter_url
            ]
            ws.append_row(new_row, value_input_option="RAW")
            logger.debug("Created weekly list id=%d for week %s", new_id, week_start_str)
            return new_id
    except Exception:
        logger.exception("Error creating weekly list for week %s", week_start)
        raise


def mark_list_published(list_id: int, newsletter_url: str = None):
    """Mark a weekly list as published."""
    try:
        ws = _get_worksheet("weekly_lists")
        # list_id maps to row list_id + 1 (1-indexed, header at row 1)
        row_idx = list_id + 1
        now = _now_iso()

        # Update published_at (col C), status (col D), newsletter_url (col F)
        ws.update(f"C{row_idx}", [[now]])
        ws.update(f"D{row_idx}", [["published"]])
        if newsletter_url:
            ws.update(f"F{row_idx}", [[newsletter_url]])

        logger.debug("Marked weekly list id=%d as published", list_id)
    except Exception:
        logger.exception("Error marking list id=%d as published", list_id)
        raise
