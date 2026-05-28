"""APScheduler job setup for periodic scraping and alert checking."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from scraper import scrape_all
from analyzer import check_and_record_alerts
from discoverer import run_discovery_cycle
from config import SCRAPE_INTERVAL_HOURS, DISCOVERY_INTERVAL_HOURS, DISCOVERY_ENABLED

logger = logging.getLogger(__name__)


def create_scheduler():
    """Create and configure the background scheduler."""
    scheduler = BackgroundScheduler()

    def job():
        logger.info("Scheduled job starting: scrape_all + check_and_record_alerts")
        try:
            scrape_all()
        except Exception as e:
            logger.error("Scheduled scrape failed: %s", e)
        try:
            check_and_record_alerts()
        except Exception as e:
            logger.error("Scheduled alert check failed: %s", e)

    scheduler.add_job(
        job,
        trigger="interval",
        hours=SCRAPE_INTERVAL_HOURS,
        id="scrape_job",
        replace_existing=True,
    )

    # Discovery job: find new stock subreddits daily
    if DISCOVERY_ENABLED:
        def discovery_job():
            logger.info("Scheduled discovery job starting")
            try:
                run_discovery_cycle()
            except Exception as e:
                logger.error("Scheduled discovery failed: %s", e)

        scheduler.add_job(
            discovery_job,
            trigger="interval",
            hours=DISCOVERY_INTERVAL_HOURS,
            id="discovery_job",
            replace_existing=True,
        )
        logger.info(
            "Scheduler configured: scrape every %dh, discovery every %dh",
            SCRAPE_INTERVAL_HOURS, DISCOVERY_INTERVAL_HOURS,
        )
    else:
        logger.info(
            "Scheduler configured with %d-hour interval (discovery disabled)",
            SCRAPE_INTERVAL_HOURS,
        )

    return scheduler
