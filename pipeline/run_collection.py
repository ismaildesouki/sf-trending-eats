"""
Main entry point for data collection.
Runs all collectors and the scoring engine.

Usage:
    python pipeline/run_collection.py
    python pipeline/run_collection.py --source yelp
    python pipeline/run_collection.py --score-only
"""

import asyncio
import argparse
import logging
import sys
from datetime import datetime, timezone

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("collection")


async def run_collection(sources: list[str] = None, skip_scoring: bool = False):
    """Run data collection from specified sources (or all)."""

    all_sources = ["yelp", "reddit", "threads", "google_places", "google_trends", "tiktok", "instagram"]
    sources = sources or all_sources

    start_time = datetime.now(timezone.utc)
    logger.info(f"Starting collection at {start_time.isoformat()}")
    logger.info(f"Sources: {', '.join(sources)}")

    results = {}

    async with httpx.AsyncClient(timeout=30) as client:

        if "yelp" in sources:
            logger.info("Collecting from Yelp...")
            from pipeline.collectors import yelp
            results["yelp"] = await yelp.run(client)

        if "reddit" in sources:
            logger.info("Collecting from Reddit...")
            from pipeline.collectors import reddit
            results["reddit"] = await reddit.run(client)

        if "threads" in sources:
            logger.info("Collecting from Threads...")
            from pipeline.collectors import threads
            results["threads"] = await threads.run(client)

        if "google_places" in sources:
            logger.info("Collecting from Google Places...")
            from pipeline.collectors import google_places
            results["google_places"] = await google_places.run(client)

        if "tiktok" in sources:
            logger.info("Collecting from TikTok via Apify...")
            from pipeline.collectors import tiktok
            results["tiktok"] = await tiktok.run(client)

        if "instagram" in sources:
            logger.info("Collecting from Instagram via Apify...")
            from pipeline.collectors import instagram
            results["instagram"] = await instagram.run(client)

    # Google Trends uses synchronous pytrends
    if "google_trends" in sources:
        logger.info("Collecting from Google Trends...")
        from pipeline.collectors import google_trends
        results["google_trends"] = google_trends.run()

    # Run scoring engine
    if not skip_scoring:
        logger.info("Computing trend scores...")
        from pipeline.scoring import engine
        results["scoring"] = engine.run()

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(f"Collection complete in {elapsed:.1f}s")

    for source, stats in results.items():
        logger.info(f"  {source}: {stats}")

    return results


def main():
    parser = argparse.ArgumentParser(description="SF Trending Eats data collection")
    parser.add_argument(
        "--source",
        choices=["yelp", "reddit", "threads", "google_places", "google_trends", "tiktok", "instagram"],
        help="Run only a specific source",
    )
    parser.add_argument(
        "--score-only",
        action="store_true",
        help="Skip collection, only run scoring",
    )
    args = parser.parse_args()

    if args.score_only:
        from pipeline.scoring import engine
        result = engine.run()
        logger.info(f"Scoring result: {result}")
    else:
        sources = [args.source] if args.source else None
        asyncio.run(run_collection(sources=sources))


if __name__ == "__main__":
    main()
