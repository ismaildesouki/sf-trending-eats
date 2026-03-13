"""
Publisher module: generates and distributes the weekly trending list.

Outputs:
  1. Beehiiv newsletter via API
  2. Social media content via OpenClaw/Genviral (writes to a JSON file
     that the OpenClaw skill picks up)
  3. Web dashboard data (writes JSON for the Next.js frontend)
"""

import json
import logging
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

import httpx

from config import settings
from pipeline.utils.db import get_latest_trending, create_weekly_list, mark_list_published

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "web" / "lib" / "data"
SOCIAL_OUTPUT = Path(__file__).parent.parent / "openclaw" / "weekly_content.json"


async def publish_weekly_list() -> dict:
    """
    Generate and publish the weekly trending list.
    Called once per week (Tuesday morning).
    """
    stats = {"newsletter_sent": False, "social_content_generated": False, "dashboard_updated": False}

    # Get the latest scored restaurants
    trending = get_latest_trending(n=settings.publishing.top_n)

    if not trending:
        logger.warning("No trending restaurants to publish")
        return stats

    # Determine the week
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday

    # Create weekly list record
    restaurant_ids = [r["restaurant_id"] for r in trending]
    list_id = create_weekly_list(week_start, restaurant_ids)

    # Format restaurant data
    restaurants_data = []
    for i, r in enumerate(trending, 1):
        restaurants_data.append({
            "rank": i,
            "name": r["name"],
            "neighborhood": r["neighborhood"],
            "cuisine_type": r["cuisine_type"],
            "score": round(r["score"], 2),
            "trending_reason": r["trending_reason"],
            "platforms_active": r["platforms_active"],
        })

    # 1. Generate newsletter content
    newsletter_html = _generate_newsletter_html(restaurants_data, week_start)
    newsletter_url = await _send_newsletter(newsletter_html, week_start)
    if newsletter_url:
        stats["newsletter_sent"] = True
        mark_list_published(list_id, newsletter_url)

    # 2. Generate social media content
    social_content = _generate_social_content(restaurants_data, week_start)
    SOCIAL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    SOCIAL_OUTPUT.write_text(json.dumps(social_content, indent=2, default=str))
    stats["social_content_generated"] = True

    # 3. Update dashboard data
    dashboard_data = {
        "week_start": str(week_start),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "restaurants": restaurants_data,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "trending.json").write_text(json.dumps(dashboard_data, indent=2))
    (OUTPUT_DIR / f"week-{week_start}.json").write_text(json.dumps(dashboard_data, indent=2))
    stats["dashboard_updated"] = True

    logger.info(f"Weekly publish complete: {stats}")
    return stats


def _generate_newsletter_html(restaurants: list[dict], week_start: date) -> str:
    """Generate the newsletter HTML content."""

    items_html = ""
    for r in restaurants:
        platforms_str = ", ".join(r.get("platforms_active", []))
        items_html += f"""
        <div style="margin-bottom: 24px; padding: 16px; background: #f8f9fa; border-radius: 8px;">
            <div style="display: flex; align-items: baseline; gap: 12px;">
                <span style="font-size: 24px; font-weight: bold; color: #e85d04;">#{r['rank']}</span>
                <div>
                    <h3 style="margin: 0; font-size: 18px;">{r['name']}</h3>
                    <p style="margin: 4px 0 0; color: #666; font-size: 14px;">
                        {r.get('neighborhood', '')} · {r.get('cuisine_type', '')}
                    </p>
                </div>
            </div>
            <p style="margin: 8px 0 0; font-size: 14px;">
                {r.get('trending_reason', 'Trending across multiple platforms')}
            </p>
            <p style="margin: 4px 0 0; font-size: 12px; color: #999;">
                Buzzing on: {platforms_str}
            </p>
        </div>
        """

    return f"""
    <div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, sans-serif;">
        <h1 style="font-size: 28px; margin-bottom: 4px;">SF Trending Eats</h1>
        <p style="color: #666; margin-top: 0;">
            Week of {week_start.strftime('%B %d, %Y')} · Top {len(restaurants)} trending restaurants
        </p>
        <p style="font-size: 15px; line-height: 1.5;">
            These restaurants are generating the most social media buzz in the
            Bay Area right now. We track signals across Yelp, Reddit, Threads,
            Google, and more to find spots that are trending before they hit
            mainstream food media.
        </p>
        {items_html}
        <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;">
        <p style="font-size: 12px; color: #999; text-align: center;">
            SF Trending Eats · Data-driven restaurant discovery
        </p>
    </div>
    """


async def _send_newsletter(html: str, week_start: date) -> str | None:
    """Send the newsletter via Beehiiv API."""
    if not settings.publishing.beehiiv_api_key:
        logger.warning("Beehiiv API key not configured, skipping newsletter send")
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.beehiiv.com/v2/publications/{settings.publishing.beehiiv_publication_id}/posts",
                headers={
                    "Authorization": f"Bearer {settings.publishing.beehiiv_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "title": f"SF Trending Eats: Week of {week_start.strftime('%B %d')}",
                    "subtitle": "The Bay Area restaurants generating the most buzz this week",
                    "content": [{"type": "html", "html": html}],
                    "status": "confirmed",
                    "send_at": None,  # Send immediately
                },
            )
            resp.raise_for_status()
            data = resp.json()
            url = data.get("data", {}).get("web_url")
            logger.info(f"Newsletter sent: {url}")
            return url

    except Exception as e:
        logger.error(f"Newsletter send failed: {e}")
        return None


def _generate_social_content(restaurants: list[dict], week_start: date) -> dict:
    """
    Generate platform-specific social media content.
    This JSON file is picked up by the OpenClaw skill for automated posting.
    """
    top_3 = restaurants[:3]
    top_3_names = ", ".join([r["name"] for r in top_3])

    return {
        "week_start": str(week_start),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "posts": {
            "tiktok": {
                "script": (
                    f"POV: You know where to eat in SF before everyone else. "
                    f"These {len(restaurants)} restaurants are BLOWING UP on social media this week. "
                    f"Number one: {top_3[0]['name']} in {top_3[0].get('neighborhood', 'SF')}. "
                    f"Number two: {top_3[1]['name']}. "
                    f"Number three: {top_3[2]['name']}. "
                    f"Follow for the weekly trending list."
                ) if len(top_3) >= 3 else "This week's trending restaurants in SF...",
                "hashtags": [
                    "#sffood", "#sanfranciscofood", "#bayareafood", "#sfrestaurants",
                    "#foodtiktok", "#trending", "#hiddengems", "#foodie",
                ],
                "caption": f"This week's top trending SF restaurants: {top_3_names}",
            },
            "instagram": {
                "carousel_slides": [
                    {
                        "text": f"SF Trending Eats: Week of {week_start.strftime('%b %d')}",
                        "subtext": f"Top {len(restaurants)} restaurants blowing up right now",
                    }
                ] + [
                    {
                        "text": f"#{r['rank']} {r['name']}",
                        "subtext": f"{r.get('neighborhood', '')} · {r.get('cuisine_type', '')}",
                        "detail": r.get("trending_reason", ""),
                    }
                    for r in restaurants[:5]
                ] + [
                    {
                        "text": "Follow @sftrendingeats",
                        "subtext": "New trending list every Tuesday",
                    }
                ],
                "caption": (
                    f"This week's top trending SF restaurants, ranked by social media buzz:\n\n"
                    + "\n".join([f"{r['rank']}. {r['name']}" for r in restaurants[:5]])
                    + "\n\nFull list in bio. Save this for later!"
                ),
                "hashtags": [
                    "#sffood", "#sanfranciscofood", "#bayareaeats", "#sfrestaurants",
                    "#foodie", "#trending", "#whereieat", "#eatsf",
                ],
            },
            "threads": {
                "text": (
                    f"Bay Area restaurants generating the most social media buzz this week:\n\n"
                    + "\n".join([
                        f"{r['rank']}. {r['name']} ({r.get('neighborhood', 'SF')})"
                        for r in restaurants[:5]
                    ])
                    + "\n\nFull list and data at sftrendingeats.com"
                ),
            },
        },
        "restaurants": restaurants,
    }


async def run():
    """Entry point for the weekly publish job."""
    return await publish_weekly_list()
