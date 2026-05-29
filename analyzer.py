"""Velocity, acceleration, and alert computations using raw SQL via SQLAlchemy."""

import logging
from datetime import datetime, timedelta, timezone, date

from sqlalchemy import text

from config import SURGE_MULTIPLIER, ORGANIC_SCORE as ORGANIC_CFG
from database import Snapshot, Alert, Watchlist, get_session

logger = logging.getLogger(__name__)


def _ensure_datetime(val):
    """Convert string timestamps from SQLite to datetime objects."""
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return val


# ── Price move cache ──────────────────────────────────────────────────────────
_price_cache = {}  # key: "{ticker}_{days}d_{date}" → (pct_change, timestamp)


# ── Market cap cache ──────────────────────────────────────────────────────────
# Cached daily: key = "{ticker}_mcap_{today}"


def get_market_cap(ticker):
    """Returns market cap in USD (raw number). Cached daily via _price_cache."""
    if not ticker:
        return None
    today = date.today().isoformat()
    cache_key = f"{ticker}_mcap_{today}"
    if cache_key in _price_cache:
        return _price_cache[cache_key]
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        mcap = info.get("marketCap")
        _price_cache[cache_key] = mcap
        return mcap
    except Exception:
        _price_cache[cache_key] = None
        return None


def format_market_cap(mcap):
    """Format market cap as human-readable string: $4.2B, $1.5T, etc."""
    if mcap is None:
        return None
    if mcap >= 1_000_000_000_000:
        return f"${mcap/1_000_000_000_000:.1f}T"
    if mcap >= 1_000_000_000:
        return f"${mcap/1_000_000_000:.1f}B"
    if mcap >= 1_000_000:
        return f"${mcap/1_000_000:.0f}M"
    return f"${mcap:,.0f}"


def get_price_move(ticker, lookback_days=1):
    """
    Fetch the percentage price move for a ticker over the last N days.
    Uses yfinance with a per-day cache to avoid redundant API calls.
    Returns None on failure (gracefully skippable).
    """
    if not ticker:
        return None

    today = date.today().isoformat()
    cache_key = f"{ticker}_{lookback_days}d_{today}"

    if cache_key in _price_cache:
        cached_val, cached_ts = _price_cache[cache_key]
        return cached_val

    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{lookback_days + 1}d")

        if hist is None or len(hist) < 2:
            return None

        old_close = hist["Close"].iloc[0]
        new_close = hist["Close"].iloc[-1]

        if old_close <= 0:
            return None

        pct_change = round((new_close - old_close) / old_close * 100, 2)
        _price_cache[cache_key] = (pct_change, datetime.now(timezone.utc).timestamp())
        return pct_change

    except Exception as e:
        logger.debug("yfinance failed for %s (%dd): %s", ticker, lookback_days, e)
        return None


def price_penalty(price_move_pct, threshold, k):
    """
    Smooth decay function.
    Returns 1.0 when price_move_pct = 0 (no penalty).
    Returns 0.5 when price_move_pct = threshold (half penalty).
    Approaches 0 at very large moves but never reaches it.
    """
    return 1.0 / (1.0 + k * abs(price_move_pct) / threshold)


def compute_organic_score(velocity_pct, ticker):
    """
    Given a velocity and optional ticker, returns a dict with:
      organic_score  — the number to sort by (velocity × combined penalty)
      price_penalty  — float 0.0–1.0 (1.0 = no penalty applied)
      price_move_1d  — float % or None
      price_move_7d  — float % or None
      price_move_30d — float % or None

    Subreddits with no ticker always get penalty=1.0 (never penalized).
    Returns velocity_pct unchanged if velocity_pct is None.
    """
    if velocity_pct is None:
        return {
            "organic_score": None,
            "price_penalty": None,
            "price_move_1d": None,
            "price_move_7d": None,
            "price_move_30d": None,
        }

    if not ticker:
        return {
            "organic_score": round(velocity_pct, 4),
            "price_penalty": 1.0,
            "price_move_1d": None,
            "price_move_7d": None,
            "price_move_30d": None,
        }

    p1 = get_price_move(ticker, lookback_days=1)
    p7 = get_price_move(ticker, lookback_days=7)
    p30 = get_price_move(ticker, lookback_days=30)

    penalties = []
    if p1 is not None:
        penalties.append(price_penalty(p1, ORGANIC_CFG["threshold_1d"], ORGANIC_CFG["k"]))
    if p7 is not None:
        penalties.append(price_penalty(p7, ORGANIC_CFG["threshold_7d"], ORGANIC_CFG["k"]))
    if p30 is not None:
        penalties.append(price_penalty(p30, ORGANIC_CFG["threshold_30d"], ORGANIC_CFG["k"]))

    combined = min(penalties) if penalties else 1.0

    return {
        "organic_score": round(velocity_pct * combined, 4),
        "price_penalty": round(combined, 4),
        "price_move_1d": p1,
        "price_move_7d": p7,
        "price_move_30d": p30,
    }


def get_velocity(subreddit, hours=24):
    """
    Compute the percentage growth in members over the last `hours` hours.

    velocity_pct = (latest_members - members_N_hours_ago) / members_N_hours_ago * 100

    If no snapshot exists from exactly `hours` ago, falls back to the oldest
    available snapshot and normalizes the growth rate to a 24h-equivalent.
    Returns None if there are fewer than 2 snapshots.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    with get_session() as session:
        # Latest snapshot
        latest_row = session.execute(
            text(
                "SELECT members, captured_at FROM snapshots "
                "WHERE subreddit = :sub AND captured_at <= :now "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"sub": subreddit, "now": now.isoformat()},
        ).fetchone()

        if latest_row is None:
            return None

        latest_members = latest_row[0]
        latest_time = latest_row[1]
        # Ensure latest_time is a datetime object (SQLite may return strings)
        if isinstance(latest_time, str):
            latest_time = datetime.fromisoformat(latest_time)

        # Snapshot closest to `hours` ago
        past_row = session.execute(
            text(
                "SELECT members, captured_at FROM snapshots "
                "WHERE subreddit = :sub AND captured_at <= :cutoff "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"sub": subreddit, "cutoff": cutoff.isoformat()},
        ).fetchone()

        if past_row is not None and past_row[0] > 0:
            # Ideal case: we have a snapshot from 24h+ ago
            velocity_pct = (latest_members - past_row[0]) / past_row[0] * 100
            return round(velocity_pct, 4)

        # Fallback: use the oldest snapshot and normalize to 24h equivalent
        oldest_row = session.execute(
            text(
                "SELECT members, captured_at FROM snapshots "
                "WHERE subreddit = :sub AND captured_at < :latest_time "
                "ORDER BY captured_at ASC LIMIT 1"
            ),
            {"sub": subreddit, "latest_time": latest_time.isoformat() if latest_time else now.isoformat()},
        ).fetchone()

        if oldest_row is None or oldest_row[0] == 0 or oldest_row[1] is None:
            return None

        # Compute raw growth and normalize to 24h
        raw_pct = (latest_members - oldest_row[0]) / oldest_row[0] * 100
        oldest_time = _ensure_datetime(oldest_row[1])
        time_diff_hours = (latest_time - oldest_time).total_seconds() / 3600

        if time_diff_hours <= 0:
            return None

        # Normalize: if growth was X% over Y hours, 24h-equivalent is X * (24/Y)
        normalized_pct = raw_pct * (hours / time_diff_hours)
        return round(normalized_pct, 4)


def get_acceleration(subreddit):
    """
    Compute acceleration: change in velocity between two consecutive windows.

    Ideal: velocity_last_24h - velocity_24h_to_48h_ago
    Fallback: split available snapshots into two halves, compute normalized
    velocity for each half, and return the difference.

    Positive = growth is speeding up. Returns None if insufficient data.
    """
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_48h = now - timedelta(hours=48)

    with get_session() as session:
        # Try ideal case first: we have 24h and 48h data
        latest_row = session.execute(
            text(
                "SELECT members FROM snapshots "
                "WHERE subreddit = :sub AND captured_at <= :now "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"sub": subreddit, "now": now.isoformat()},
        ).fetchone()

        row_24h = session.execute(
            text(
                "SELECT members FROM snapshots "
                "WHERE subreddit = :sub AND captured_at <= :cutoff "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"sub": subreddit, "cutoff": cutoff_24h.isoformat()},
        ).fetchone()

        row_48h = session.execute(
            text(
                "SELECT members FROM snapshots "
                "WHERE subreddit = :sub AND captured_at <= :cutoff "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"sub": subreddit, "cutoff": cutoff_48h.isoformat()},
        ).fetchone()

        if (
            latest_row is not None
            and row_24h is not None
            and row_48h is not None
            and row_24h[0] > 0
            and row_48h[0] > 0
        ):
            velocity_last_24h = (latest_row[0] - row_24h[0]) / row_24h[0] * 100
            velocity_24h_to_48h = (row_24h[0] - row_48h[0]) / row_48h[0] * 100
            acceleration = velocity_last_24h - velocity_24h_to_48h
            return round(acceleration, 4)

        # Fallback: split all snapshots into two halves and compare velocities
        rows = session.execute(
            text(
                "SELECT captured_at, members FROM snapshots "
                "WHERE subreddit = :sub ORDER BY captured_at ASC"
            ),
            {"sub": subreddit},
        ).fetchall()

        if len(rows) < 3:
            return None

        mid = len(rows) // 2
        first_half = rows[:mid]
        second_half = rows[mid:]

        def _half_velocity(half):
            if len(half) < 2 or half[0][1] == 0:
                return None
            raw_pct = (half[-1][1] - half[0][1]) / half[0][1] * 100
            t_start = _ensure_datetime(half[0][0])
            t_end = _ensure_datetime(half[-1][0])
            time_diff_hours = (t_end - t_start).total_seconds() / 3600
            if time_diff_hours <= 0:
                return None
            return raw_pct * (24 / time_diff_hours)

        v_first = _half_velocity(first_half)
        v_second = _half_velocity(second_half)

        if v_first is None or v_second is None:
            return None

        acceleration = v_second - v_first
        return round(acceleration, 4)


def get_leaderboard(limit=20, ticker_only=False):
    """
    Return a list of dicts for each subreddit, sorted by velocity_pct descending.

    Each dict contains:
        subreddit, ticker, members, velocity_pct, acceleration,
        members_7d_ago (for sparkline baseline)

    Only includes subreddits with at least 2 snapshots.
    If ticker_only=True, only include subreddits with a non-null ticker.
    """
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)

    results = []

    with get_session() as session:
        query = session.query(Watchlist.subreddit, Watchlist.ticker).filter_by(active=True)
        if ticker_only:
            query = query.filter(Watchlist.ticker.isnot(None))
        active_entries = query.all()

    for entry in active_entries:
        subreddit_name = entry.subreddit
        ticker = entry.ticker
        with get_session() as session:
            # Count snapshots
            count_row = session.execute(
                text(
                    "SELECT COUNT(*) FROM snapshots WHERE subreddit = :sub"
                ),
                {"sub": subreddit_name},
            ).fetchone()

            if count_row is None or count_row[0] < 2:
                continue

            # Latest snapshot
            latest_row = session.execute(
                text(
                    "SELECT members, captured_at FROM snapshots "
                    "WHERE subreddit = :sub "
                    "ORDER BY captured_at DESC LIMIT 1"
                ),
                {"sub": subreddit_name},
            ).fetchone()

            if latest_row is None:
                continue

            members = latest_row[0]

            # Snapshot closest to 7 days ago
            row_7d = session.execute(
                text(
                    "SELECT members FROM snapshots "
                    "WHERE subreddit = :sub AND captured_at <= :cutoff "
                    "ORDER BY captured_at DESC LIMIT 1"
                ),
                {"sub": subreddit_name, "cutoff": cutoff_7d.isoformat()},
            ).fetchone()

            if row_7d is not None:
                members_7d_ago = row_7d[0]
            else:
                # Fallback: use the oldest snapshot as baseline
                oldest = session.execute(
                    text("SELECT members FROM snapshots WHERE subreddit = :sub ORDER BY captured_at ASC LIMIT 1"),
                    {"sub": subreddit_name},
                ).fetchone()
                members_7d_ago = oldest[0] if oldest is not None else None

        velocity = get_velocity(subreddit_name, hours=24)
        acceleration = get_acceleration(subreddit_name)

        row = {
            "subreddit": subreddit_name,
            "ticker": entry.ticker,
            "members": members,
            "velocity_pct": velocity,
            "acceleration": acceleration,
            "members_7d_ago": members_7d_ago,
        }

        # Compute organic score and merge into row
        organic = compute_organic_score(velocity, entry.ticker)
        row.update(organic)

        # Remove legacy key if present
        row.pop("price_driven", None)

        # Market cap (cached daily per ticker)
        mcap = get_market_cap(entry.ticker)
        row["market_cap"] = mcap
        row["market_cap_fmt"] = format_market_cap(mcap)

        results.append(row)

    # Sort by organic_score descending; None values go to the end
    results.sort(key=lambda x: x["organic_score"] if x["organic_score"] is not None else float("-inf"), reverse=True)

    return results[:limit]


def get_history(subreddit, days=30):
    """
    Return a list of {"timestamp": iso_string, "members": int} for the past N days,
    one entry per snapshot. Used to draw sparklines.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with get_session() as session:
        rows = session.execute(
            text(
                "SELECT captured_at, members FROM snapshots "
                "WHERE subreddit = :sub AND captured_at >= :cutoff "
                "ORDER BY captured_at ASC"
            ),
            {"sub": subreddit, "cutoff": cutoff.isoformat()},
        ).fetchall()

    return [
        {
            "timestamp": _ensure_datetime(row[0]).isoformat() if row[0] else None,
            "members": row[1],
        }
        for row in rows
    ]


def check_and_record_alerts():
    """
    For each subreddit:
      1. Compute 24h velocity
      2. Compute 30-day average velocity (average of all daily velocities in the window)
      3. If velocity_24h > SURGE_MULTIPLIER * avg_30d_velocity, insert an Alert record
      4. Return list of newly triggered alerts
    """
    now = datetime.now(timezone.utc)
    cutoff_30d = now - timedelta(days=30)
    new_alerts = []

    with get_session() as session:
        active_entries = (
            session.query(Watchlist.subreddit, Watchlist.ticker)
            .filter_by(active=True)
            .all()
        )

    for entry in active_entries:
        subreddit_name = entry.subreddit
        ticker = entry.ticker
        velocity_24h = get_velocity(subreddit_name, hours=24)

        if velocity_24h is None:
            continue

        # Compute 30-day average velocity
        # We look at daily snapshots and compute the average daily velocity
        with get_session() as session:
            rows = session.execute(
                text(
                    "SELECT captured_at, members FROM snapshots "
                    "WHERE subreddit = :sub AND captured_at >= :cutoff "
                    "ORDER BY captured_at ASC"
                ),
                {"sub": subreddit_name, "cutoff": cutoff_30d.isoformat()},
            ).fetchall()

        if len(rows) < 2:
            continue

        # Compute daily velocities between consecutive snapshots
        daily_velocities = []
        for i in range(1, len(rows)):
            prev_members = rows[i - 1][1]
            curr_members = rows[i][1]
            prev_time = rows[i - 1][0]
            curr_time = rows[i][0]

            if prev_members == 0 or prev_time is None or curr_time is None:
                continue

            # Normalize to daily velocity
            prev_dt = _ensure_datetime(prev_time)
            curr_dt = _ensure_datetime(curr_time)
            time_diff_hours = (curr_dt - prev_dt).total_seconds() / 3600
            if time_diff_hours <= 0:
                continue

            pct_change = (curr_members - prev_members) / prev_members * 100
            daily_velocity = pct_change * (24 / time_diff_hours)  # normalize to 24h
            daily_velocities.append(daily_velocity)

        if not daily_velocities:
            continue

        avg_30d_velocity = sum(daily_velocities) / len(daily_velocities)

        # Check surge condition
        # Only alert if baseline is positive (avoid division issues with zero/negative)
        if avg_30d_velocity <= 0:
            continue

        multiplier = velocity_24h / avg_30d_velocity

        if multiplier >= SURGE_MULTIPLIER:
            with get_session() as session:
                alert = Alert(
                    subreddit=subreddit_name,
                    ticker=ticker,
                    velocity_pct=velocity_24h,
                    baseline_velocity_pct=round(avg_30d_velocity, 4),
                    multiplier=round(multiplier, 2),
                )
                session.add(alert)

            new_alerts.append(
                {
                    "subreddit": subreddit_name,
                    "ticker": ticker,
                    "velocity_pct": velocity_24h,
                    "baseline_velocity_pct": round(avg_30d_velocity, 4),
                    "multiplier": round(multiplier, 2),
                }
            )
            logger.info(
                "SURGE ALERT: r/%s velocity %.2f%% is %.1fx the 30d avg %.2f%%",
                subreddit_name,
                velocity_24h,
                multiplier,
                avg_30d_velocity,
            )

    return new_alerts