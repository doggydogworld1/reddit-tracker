"""
discoverer.py — Expanded subreddit discovery engine.
Four discovery methods:
  1. discover_from_tickers()       — probe S&P 500 ticker names (slow, one-time)
  2. discover_from_reddit_search() — search Reddit for stock communities (fast, every cycle)
  3. discover_from_related()       — parse related_subreddits field from about.json
  4. promote_approved_discoveries()— quality-filter pending discoveries and add to Watchlist
"""

import logging
import time
import threading

import requests
import pandas as pd
from sqlalchemy import text

from database import get_session, Watchlist
from config import SCRAPE_HEADERS

logger = logging.getLogger(__name__)

# Global stop flag for the ticker seed job
_seed_stop_event = threading.Event()

# ── Quality filter ────────────────────────────────────────────────────────────

FALSE_POSITIVE_WORDS = {
    "food", "music", "gaming", "nfl", "nba", "nhl", "mlb", "travel",
    "cooking", "fitness", "movies", "anime", "manga", "sports", "soccer",
    "football", "basketball", "baseball", "hockey", "wrestling", "mma",
    "cars", "automotive", "pets", "dogs", "cats", "funny", "memes",
    "politics", "news", "science", "space", "history", "art", "design",
    "fashion", "beauty", "makeup", "relationships", "dating", "parenting",
}

FINANCE_KEYWORDS = {
    "stock", "invest", "trading", "shares", "market", "ticker", "equity",
    "portfolio", "finance", "options", "dividend", "etf", "fund", "bull",
    "bear", "nasdaq", "nyse", "earnings", "hedge", "short", "long",
    "wallstreet", "stonk", "ape", "yolo", "dd", "due diligence",
}


def _is_finance_subreddit(name, description):
    """Return True if this subreddit is likely finance-related."""
    name_lower = name.lower()
    # Reject if name contains false positive words
    for word in FALSE_POSITIVE_WORDS:
        if word in name_lower:
            return False
    # Accept if name or description contains finance keywords
    combined = name_lower + " " + (description or "").lower()
    return any(kw in combined for kw in FINANCE_KEYWORDS)


def _upsert_discovery(subreddit, ticker_guess, members, discovered_via, description=""):
    """Insert into discovered_subreddits if not already present. Uses INSERT OR IGNORE for SQLite."""
    with get_session() as session:
        session.execute(text(
            "INSERT OR IGNORE INTO discovered_subreddits "
            "(subreddit, ticker, members, source, discovered_via, ticker_guess, description, approved, status) "
            "VALUES (:sub, :ticker, :members, :via, :via, :tg, :desc, 0, 'pending')"
        ), {
            "sub": subreddit,
            "ticker": ticker_guess,
            "members": members,
            "via": discovered_via,
            "tg": ticker_guess,
            "desc": description,
        })


def _fetch_about(subreddit):
    """Fetch /r/{subreddit}/about.json. Returns data dict or None on failure."""
    try:
        url = f"https://www.reddit.com/r/{subreddit}/about.json"
        r = requests.get(url, headers=SCRAPE_HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get("data", {})
        return None
    except Exception as e:
        logger.debug("fetch_about failed for r/%s: %s", subreddit, e)
        return None


# ── Method 1: S&P 500 ticker probe ───────────────────────────────────────────

def _generate_candidates(ticker, company_name):
    """Generate candidate subreddit names from a ticker and company name."""
    ticker_clean = ticker.lower().replace(".", "").replace("-", "")
    # Clean company name: remove legal suffixes, lowercase, no spaces
    company = company_name.lower()
    for suffix in [" inc", " corp", " ltd", " llc", " co", " plc", " group",
                   " holdings", " technologies", " technology", " systems",
                   " international", " global", ",", ".", "&"]:
        company = company.replace(suffix, "")
    company = company.strip().replace(" ", "")
    first_word = company.split()[0] if " " in company_name.lower() else company

    candidates = list(dict.fromkeys([  # deduplicate preserving order
        ticker_clean,
        f"{ticker_clean}stock",
        f"{ticker_clean}investors",
        f"invest{ticker_clean}",
        company,
        f"{company}stock",
        f"{first_word}investors",
        f"{first_word}stock",
    ]))
    return [c for c in candidates if 2 < len(c) < 30]


def discover_from_tickers():
    """
    One-time seed job: probe S&P 500 tickers as subreddit names.
    Runs in background — takes 2-4 hours for full S&P 500 candidate list.
    Respects _seed_stop_event for clean shutdown.
    """
    _seed_stop_event.clear()
    logger.info("Starting ticker seed discovery job...")
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        df = tables[0]
        tickers = list(zip(df["Symbol"].tolist(), df["Security"].tolist()))
        logger.info("Loaded %d S&P 500 tickers", len(tickers))
    except Exception as e:
        logger.error("Failed to fetch S&P 500 list: %s", e)
        return

    probed = 0
    found = 0
    for ticker, company in tickers:
        if _seed_stop_event.is_set():
            logger.info("Ticker seed job stopped early by stop event")
            break
        candidates = _generate_candidates(ticker, company)
        for candidate in candidates:
            if _seed_stop_event.is_set():
                break
            data = _fetch_about(candidate)
            probed += 1
            if data and data.get("subscribers", 0) >= 500:
                desc = data.get("public_description", "") or data.get("description", "")
                if _is_finance_subreddit(candidate, desc):
                    _upsert_discovery(candidate, ticker.upper(), data["subscribers"], "ticker_probe", desc)
                    found += 1
                    logger.info("Found: r/%s (%s members) via $%s", candidate, f"{data['subscribers']:,}", ticker)
            time.sleep(2)

    logger.info("Ticker seed job complete. Probed %d candidates, found %d finance subreddits.", probed, found)


def stop_seed_job():
    """Signal the ticker seed job to stop."""
    _seed_stop_event.set()


# ── Method 2: Reddit search ───────────────────────────────────────────────────

SEARCH_TERMS = [
    "stock investing", "stock market", "stock trading", "share trading",
    "equity investing", "options trading", "dividend investing",
    "penny stocks", "growth stocks", "value investing",
]


def discover_from_reddit_search(query_terms=None):
    """Search Reddit's subreddit search for stock communities. Fast — ~10 requests."""
    terms = query_terms or SEARCH_TERMS
    found = 0
    for term in terms:
        try:
            url = f"https://www.reddit.com/search.json?q={requests.utils.quote(term)}&type=sr&limit=25"
            r = requests.get(url, headers=SCRAPE_HEADERS, timeout=10)
            if r.status_code != 200:
                time.sleep(2)
                continue
            children = r.json().get("data", {}).get("children", [])
            for child in children:
                d = child.get("data", {})
                name = d.get("display_name", "")
                members = d.get("subscribers", 0)
                desc = d.get("public_description", "") or ""
                if members >= 500 and _is_finance_subreddit(name, desc):
                    _upsert_discovery(name, None, members, "search", desc)
                    found += 1
            time.sleep(2)
        except Exception as e:
            logger.warning("Search discovery failed for '%s': %s", term, e)
    logger.info("Search discovery found %d new candidates", found)


# ── Method 3: Related subreddits ──────────────────────────────────────────────

def discover_from_related(subreddit_name):
    """Parse related_subreddits from a subreddit's about.json."""
    data = _fetch_about(subreddit_name)
    if not data:
        return
    related = data.get("related_subreddits", []) or []
    for item in related:
        name = item.get("name", "").lstrip("r/")
        if name:
            sub_data = _fetch_about(name)
            if sub_data and sub_data.get("subscribers", 0) >= 500:
                desc = sub_data.get("public_description", "") or ""
                if _is_finance_subreddit(name, desc):
                    _upsert_discovery(name, None, sub_data["subscribers"], "related", desc)
            time.sleep(2)


# ── Method 4: Promote to watchlist ────────────────────────────────────────────

def promote_approved_discoveries(min_members=1000):
    """
    Promote pending discoveries that pass quality filter to the Watchlist table.
    Called at the end of every scrape cycle.
    """
    with get_session() as session:
        rows = session.execute(text(
            "SELECT subreddit, ticker_guess, members, description "
            "FROM discovered_subreddits "
            "WHERE status = 'pending' AND members >= :min"
        ), {"min": min_members}).fetchall()

    promoted = 0
    for row in rows:
        subreddit, ticker_guess, members, description = row
        # Re-verify it still exists and passes quality filter
        data = _fetch_about(subreddit)
        if not data:
            continue
        current_members = data.get("subscribers", 0)
        desc = data.get("public_description", "") or description or ""
        if current_members < min_members:
            continue
        if not _is_finance_subreddit(subreddit, desc):
            # Auto-reject obvious false positives
            with get_session() as session:
                session.execute(text(
                    "UPDATE discovered_subreddits SET status='rejected' WHERE subreddit=:sub"
                ), {"sub": subreddit})
            continue
        # Add to Watchlist
        with get_session() as session:
            existing = session.execute(text(
                "SELECT id FROM watchlist WHERE subreddit=:sub"
            ), {"sub": subreddit}).fetchone()
            if not existing:
                session.add(Watchlist(
                    subreddit=subreddit,
                    ticker=ticker_guess,
                    auto_discovered=True,
                    active=True,
                ))
            # Update discovered_subreddits status
            session.execute(text(
                "UPDATE discovered_subreddits SET status='promoted', approved=1 WHERE subreddit=:sub"
            ), {"sub": subreddit})
        promoted += 1
        time.sleep(1)

    if promoted:
        logger.info("Promoted %d discovered subreddits to watchlist", promoted)


# ── Combined run (called from scheduler) ─────────────────────────────────────

def run_discovery_cycle():
    """
    Fast discovery cycle — called every 24h from scheduler.
    Does NOT run ticker probe (that's manual via /admin/seed).
    """
    discover_from_reddit_search()
    # Crawl related subs from top 5 most-tracked subreddits
    try:
        with get_session() as session:
            top = session.execute(text(
                "SELECT DISTINCT subreddit FROM snapshots "
                "ORDER BY members DESC LIMIT 5"
            )).fetchall()
        for (sub,) in top:
            discover_from_related(sub)
    except Exception as e:
        logger.warning("Related discovery error: %s", e)
    promote_approved_discoveries()