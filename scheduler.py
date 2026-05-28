"""APScheduler job setup for periodic scraping and alert checking."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from scraper import scrape_all
from analyzer import check_and_record_alerts
from config import SCRAPE_INTERVAL_HOURS

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

    logger.info(
        "Scheduler configured with %d-hour interval", SCRAPE_INTERVAL_HOURS
    )
    return scheduler