"""Requests-based Reddit scraper for subreddit membership data."""

import logging
import time

import requests

from database import Snapshot, Watchlist, get_session

logger = logging.getLogger(__name__)

# Browser-like User-Agent to avoid Reddit blocking generic request agents
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}

_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)


def get_active_watchlist():
    """Return list of (subreddit, ticker) tuples from the DB watchlist."""
    with get_session() as session:
        entries = session.query(Watchlist).filter_by(active=True).all()
        return [(e.subreddit, e.ticker) for e in entries]


def scrape_all():
    """
    For each active subreddit in the DB watchlist:
      1. GET https://www.reddit.com/r/{name}/about.json
      2. Extract subscribers as members and accounts_active as active_users
      3. Create a Snapshot record and commit to DB
      4. Log success or failure per subreddit
      5. Sleep 2 seconds between requests to respect rate limits
    Catch all exceptions per-subreddit so one failure doesn't stop the rest.
    """
    watchlist = get_active_watchlist()
    logger.info("Starting scrape cycle for %d subreddits", len(watchlist))
    success_count = 0
    fail_count = 0

    for subreddit_name, ticker in watchlist:
        try:
            url = f"https://www.reddit.com/r/{subreddit_name}/about.json"
            resp = _SESSION.get(url, timeout=15)
            resp.raise_for_status()

            data = resp.json().get("data", {})
            members = data.get("subscribers")
            active_users = data.get("accounts_active")

            # Reddit may return None for some fields
            if members is None:
                logger.warning(
                    "r/%s returned no subscriber count — skipping", subreddit_name
                )
                fail_count += 1
                continue

            if active_users is None:
                logger.debug("active_users is None for r/%s", subreddit_name)

            with get_session() as session:
                snapshot = Snapshot(
                    subreddit=subreddit_name,
                    ticker=ticker,
                    members=members,
                    active_users=active_users,
                )
                session.add(snapshot)

            logger.info(
                "Scraped r/%s: %d members, %s active",
                subreddit_name,
                members,
                active_users if active_users is not None else "N/A",
            )
            success_count += 1

        except Exception as e:
            logger.error("Failed to scrape r/%s: %s", subreddit_name, e)
            fail_count += 1

        # Sleep 2 seconds between requests to respect rate limits
        time.sleep(2)

    logger.info(
        "Scrape cycle complete: %d succeeded, %d failed", success_count, fail_count
    )