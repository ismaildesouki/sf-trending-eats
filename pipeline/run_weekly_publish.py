"""
Weekly publishing entry point.
Generates the newsletter, social content, and dashboard data.

Usage:
    python pipeline/run_weekly_publish.py
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("publisher")


async def main():
    logger.info("Starting weekly publish...")

    # First ensure we have fresh scores
    from pipeline.scoring import engine
    score_result = engine.run()
    logger.info(f"Scoring: {score_result}")

    # Publish
    from pipeline.publisher import publish_weekly_list
    result = await publish_weekly_list()
    logger.info(f"Publish result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
