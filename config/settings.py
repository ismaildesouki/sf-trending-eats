"""
Central configuration for SF Trending Eats pipeline.
Loads from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SheetsConfig:
    spreadsheet_id: str = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    credentials_file: str = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "credentials.json")


@dataclass
class YelpConfig:
    api_key: str = os.getenv("YELP_API_KEY", "")
    base_url: str = "https://api.yelp.com/v3"
    location: str = "San Francisco, CA"
    radius: int = 40000  # meters (~25 miles, covers Bay Area core)
    search_limit: int = 50


@dataclass
class RedditConfig:
    client_id: str = os.getenv("REDDIT_CLIENT_ID", "")
    client_secret: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    user_agent: str = os.getenv("REDDIT_USER_AGENT", "sf-trending-eats/1.0")
    subreddits: list = field(default_factory=lambda: [
        "SFFood",
        "sanfrancisco",
        "bayarea",
        "oakland",
        "AskSF",
        "sanjose",
    ])
    posts_per_sub: int = 100  # hot + new posts to scan per sub


@dataclass
class ThreadsConfig:
    access_token: str = os.getenv("THREADS_ACCESS_TOKEN", "")
    keywords: list = field(default_factory=lambda: [
        "sf restaurant",
        "san francisco food",
        "bay area eats",
        "sf food",
        "oakland restaurant",
        "sf brunch",
        "sf dinner",
        "sf ramen",
        "sf tacos",
        "sf pizza",
    ])


@dataclass
class GooglePlacesConfig:
    api_key: str = os.getenv("GOOGLE_PLACES_API_KEY", "")
    location: str = "37.7749,-122.4194"  # SF center
    radius: int = 40000


@dataclass
class ScoringConfig:
    """Weights for the composite trend score."""
    mention_velocity_weight: float = 0.30
    engagement_accel_weight: float = 0.25
    cross_platform_weight: float = 0.20
    sentiment_weight: float = 0.15
    influencer_signal_weight: float = 0.10

    # A restaurant must appear on this many platforms to get cross-platform bonus
    min_platforms_for_bonus: int = 2

    # Minimum mentions in the scoring window to be considered
    min_mentions: int = int(os.getenv("MIN_MENTIONS_TO_RANK", "3"))

    # Standard deviations above mean to flag as "trending"
    trend_threshold: float = float(os.getenv("TREND_SCORE_THRESHOLD", "2.0"))

    # Rolling baseline window for velocity computation
    baseline_days: int = 30

    # Scoring window (recent activity)
    scoring_window_hours: int = 168  # 7 days


@dataclass
class PublishingConfig:
    beehiiv_api_key: str = os.getenv("BEEHIIV_API_KEY", "")
    beehiiv_publication_id: str = os.getenv("BEEHIIV_PUBLICATION_ID", "")
    genviral_api_key: str = os.getenv("GENVIRAL_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    top_n: int = int(os.getenv("TOP_N_RESTAURANTS", "10"))
    newsletter_day: str = os.getenv("NEWSLETTER_SEND_DAY", "tuesday")


@dataclass
class GeoConfig:
    """Bay Area bounding box for filtering results."""
    lat_center: float = float(os.getenv("GEO_LAT_CENTER", "37.7749"))
    lng_center: float = float(os.getenv("GEO_LNG_CENTER", "-122.4194"))
    radius_meters: int = int(os.getenv("GEO_RADIUS_METERS", "50000"))

    # Neighborhood mapping for SF
    neighborhoods: dict = field(default_factory=lambda: {
        "mission": {"lat": 37.7599, "lng": -122.4148},
        "soma": {"lat": 37.7785, "lng": -122.3950},
        "castro": {"lat": 37.7609, "lng": -122.4350},
        "hayes_valley": {"lat": 37.7762, "lng": -122.4250},
        "richmond": {"lat": 37.7800, "lng": -122.4700},
        "sunset": {"lat": 37.7533, "lng": -122.4900},
        "nob_hill": {"lat": 37.7930, "lng": -122.4161},
        "chinatown": {"lat": 37.7941, "lng": -122.4078},
        "north_beach": {"lat": 37.8060, "lng": -122.4103},
        "marina": {"lat": 37.8015, "lng": -122.4368},
        "fillmore": {"lat": 37.7849, "lng": -122.4320},
        "tenderloin": {"lat": 37.7847, "lng": -122.4141},
        "dogpatch": {"lat": 37.7619, "lng": -122.3870},
        "inner_sunset": {"lat": 37.7601, "lng": -122.4658},
        "outer_sunset": {"lat": 37.7533, "lng": -122.4970},
        "noe_valley": {"lat": 37.7502, "lng": -122.4337},
        "bernal_heights": {"lat": 37.7388, "lng": -122.4156},
        "potrero_hill": {"lat": 37.7583, "lng": -122.3981},
        "oakland_downtown": {"lat": 37.8044, "lng": -122.2712},
        "oakland_temescal": {"lat": 37.8370, "lng": -122.2600},
        "berkeley_downtown": {"lat": 37.8716, "lng": -122.2727},
    })


@dataclass
class TikTokConfig:
    apify_token: str = os.getenv("APIFY_TOKEN", "")
    hashtags: list = field(default_factory=lambda: [
        "sffood", "sfrestaurants", "sanfranciscofood", "bayareaeats",
        "sfeats", "oaklandfood", "sfbrunch", "sfdining",
        "bayareafoodie", "sffoodies",
    ])
    results_per_hashtag: int = int(os.getenv("TIKTOK_RESULTS_PER_HASHTAG", "50"))


@dataclass
class InstagramConfig:
    apify_token: str = os.getenv("APIFY_TOKEN", "")
    hashtags: list = field(default_factory=lambda: [
        "sffood", "sfrestaurants", "sanfranciscofood", "bayareaeats",
        "sfeats", "oaklandfood", "sfbrunch", "sfdining",
        "bayareafoodie", "sffoodie",
    ])
    results_per_hashtag: int = int(os.getenv("INSTAGRAM_RESULTS_PER_HASHTAG", "50"))


@dataclass
class EntityResolverConfig:
    api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model: str = os.getenv("ENTITY_RESOLVER_MODEL", "claude-sonnet-4-20250514")
    batch_size: int = int(os.getenv("ENTITY_RESOLVER_BATCH_SIZE", "20"))
    min_confidence: float = float(os.getenv("ENTITY_RESOLVER_MIN_CONFIDENCE", "0.5"))


# Singleton config instances
db = SheetsConfig()
yelp = YelpConfig()
reddit = RedditConfig()
threads = ThreadsConfig()
google_places = GooglePlacesConfig()
scoring = ScoringConfig()
publishing = PublishingConfig()
geo = GeoConfig()
tiktok = TikTokConfig()
instagram = InstagramConfig()
entity_resolver = EntityResolverConfig()
