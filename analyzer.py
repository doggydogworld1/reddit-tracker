"""Velocity, acceleration, and alert computations using raw SQL via SQLAlchemy."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from config import SURGE_MULTIPLIER
from database import Snapshot, Alert, Watchlist, get_session

logger = logging.getLogger(__name__)


def get_velocity(subreddit, hours=24):
    """
    Compute the percentage growth in members over the last `hours` hours.

    velocity_pct = (latest_members - members_N_hours_ago) / members_N_hours_ago * 100

    Returns None if there is no snapshot older than `hours` for comparison.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    with get_session() as session:
        # Latest snapshot
        latest_row = session.execute(
            text(
                "SELECT members FROM snapshots "
                "WHERE subreddit = :sub AND captured_at <= :now "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"sub": subreddit, "now": datetime.now(timezone.utc).isoformat()},
        ).fetchone()

        if latest_row is None:
            return None

        # Snapshot closest to `hours` ago
        past_row = session.execute(
            text(
                "SELECT members FROM snapshots "
                "WHERE subreddit = :sub AND captured_at <= :cutoff "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"sub": subreddit, "cutoff": cutoff.isoformat()},
        ).fetchone()

        if past_row is None or past_row[0] == 0:
            return None

        velocity_pct = (latest_row[0] - past_row[0]) / past_row[0] * 100
        return round(velocity_pct, 4)


def get_acceleration(subreddit):
    """
    Compute acceleration: change in velocity between two consecutive 24h windows.

    acceleration = velocity_last_24h - velocity_24h_to_48h_ago

    Positive = growth is speeding up. Returns None if insufficient data.
    """
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_48h = now - timedelta(hours=48)

    with get_session() as session:
        # Latest snapshot
        latest_row = session.execute(
            text(
                "SELECT members FROM snapshots "
                "WHERE subreddit = :sub AND captured_at <= :now "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"sub": subreddit, "now": now.isoformat()},
        ).fetchone()

        # Snapshot ~24h ago
        row_24h = session.execute(
            text(
                "SELECT members FROM snapshots "
                "WHERE subreddit = :sub AND captured_at <= :cutoff "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"sub": subreddit, "cutoff": cutoff_24h.isoformat()},
        ).fetchone()

        # Snapshot ~48h ago
        row_48h = session.execute(
            text(
                "SELECT members FROM snapshots "
                "WHERE subreddit = :sub AND captured_at <= :cutoff "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"sub": subreddit, "cutoff": cutoff_48h.isoformat()},
        ).fetchone()

        if (
            latest_row is None
            or row_24h is None
            or row_48h is None
            or row_24h[0] == 0
            or row_48h[0] == 0
        ):
            return None

        velocity_last_24h = (latest_row[0] - row_24h[0]) / row_24h[0] * 100
        velocity_24h_to_48h = (row_24h[0] - row_48h[0]) / row_48h[0] * 100

        acceleration = velocity_last_24h - velocity_24h_to_48h
        return round(acceleration, 4)


def get_leaderboard(limit=20):
    """
    Return a list of dicts for each subreddit, sorted by velocity_pct descending.

    Each dict contains:
        subreddit, ticker, members, velocity_pct, acceleration,
        members_7d_ago (for sparkline baseline)

    Only includes subreddits with at least 2 snapshots.
    """
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)

    results = []

    with get_session() as session:
        active_entries = session.query(Watchlist).filter_by(active=True).all()

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

            members_7d_ago = row_7d[0] if row_7d is not None else None

        velocity = get_velocity(subreddit_name, hours=24)
        acceleration = get_acceleration(subreddit_name)

        results.append(
            {
                "subreddit": subreddit_name,
                "ticker": entry.ticker,
                "members": members,
                "velocity_pct": velocity,
                "acceleration": acceleration,
                "members_7d_ago": members_7d_ago,
            }
        )

    # Sort by velocity_pct descending; None values go to the end
    results.sort(key=lambda x: x["velocity_pct"] if x["velocity_pct"] is not None else float("-inf"), reverse=True)

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
        {"timestamp": row[0].isoformat() if row[0] else None, "members": row[1]}
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
        active_entries = session.query(Watchlist).filter_by(active=True).all()

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
            time_diff_hours = (curr_time - prev_time).total_seconds() / 3600
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