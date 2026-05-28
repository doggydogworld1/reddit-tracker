"""Flask web application for the Reddit Stock Community Velocity Tracker."""

import logging
from datetime import datetime, timedelta, timezone

from flask import Flask, render_template, jsonify, request
from sqlalchemy import text as sa_text

import threading

from config import FLASK_PORT, FLASK_DEBUG, WATCHLIST, ADMIN_SEED_TOKEN
from database import init_db, Snapshot, Alert, get_session
from scraper import scrape_all
from analyzer import get_leaderboard, get_history, check_and_record_alerts
from discoverer import discover_from_tickers, stop_seed_job, promote_approved_discoveries, run_discovery_cycle
from scheduler import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def _to_iso(val):
    """Safely convert a datetime (or string from SQLite) to ISO format."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return val.isoformat()


@app.route("/")
def dashboard():
    """Render the single-page dashboard."""
    leaderboard_data = get_leaderboard(20)

    with get_session() as session:
        row = session.execute(
            sa_text("SELECT MAX(captured_at) FROM snapshots")
        ).fetchone()
        last_updated = _to_iso(row[0]) if row and row[0] else None

        cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
        alert_row = session.execute(
            sa_text(
                "SELECT COUNT(*) FROM alerts WHERE triggered_at >= :cutoff"
            ),
            {"cutoff": cutoff_7d.isoformat()},
        ).fetchone()
        alert_count = alert_row[0] if alert_row else 0

        snap_row = session.execute(
            sa_text("SELECT COUNT(*) FROM snapshots")
        ).fetchone()
        snapshot_count = snap_row[0] if snap_row else 0

    return render_template(
        "dashboard.html",
        leaderboard=leaderboard_data,
        last_updated=last_updated,
        alert_count=alert_count,
        snapshot_count=snapshot_count,
        total_subreddits=len(WATCHLIST),
    )


@app.route("/api/leaderboard")
def api_leaderboard():
    """Return leaderboard data as JSON. ?sort=organic (default) or ?sort=velocity. ?ticker_only=true (default)."""
    limit = request.args.get("limit", 50, type=int)
    sort = request.args.get("sort", "organic")
    ticker_only = request.args.get("ticker_only", "true").lower() == "true"
    data = get_leaderboard(limit, ticker_only=ticker_only)
    if sort == "velocity":
        data = sorted(data, key=lambda r: r["velocity_pct"] or 0, reverse=True)
    # organic sort is already default from get_leaderboard()
    return jsonify(data)


@app.route("/api/history/<subreddit>")
def api_history(subreddit):
    """Return historical membership data for a subreddit as JSON."""
    days = request.args.get("days", 30, type=int)
    data = get_history(subreddit, days=days)
    return jsonify(data)


@app.route("/api/alerts")
def api_alerts():
    """Return last 50 alerts as JSON, newest first."""
    with get_session() as session:
        rows = session.execute(
            sa_text(
                "SELECT id, subreddit, ticker, velocity_pct, "
                "baseline_velocity_pct, multiplier, triggered_at "
                "FROM alerts ORDER BY triggered_at DESC LIMIT 50"
            )
        ).fetchall()

        alerts = [
            {
                "id": row[0],
                "subreddit": row[1],
                "ticker": row[2],
                "velocity_pct": row[3],
                "baseline_velocity_pct": row[4],
                "multiplier": row[5],
                "triggered_at": _to_iso(row[6]) if row[6] else None,
            }
            for row in rows
        ]

    return jsonify(alerts)


@app.route("/api/discoveries")
def api_discoveries():
    """Pending discovered subreddits for review."""
    with get_session() as session:
        rows = session.execute(sa_text(
            "SELECT subreddit, ticker_guess, members, discovered_via, discovered_at, status "
            "FROM discovered_subreddits "
            "WHERE status = 'pending' "
            "ORDER BY members DESC LIMIT 200"
        )).fetchall()
    return jsonify([{
        "subreddit": r[0], "ticker_guess": r[1], "members": r[2],
        "discovered_via": r[3], "discovered_at": str(r[4]), "status": r[5]
    } for r in rows])


@app.route("/api/discoveries/<subreddit>/approve", methods=["POST"])
def approve_discovery(subreddit):
    """Approve a pending discovery and add it to the watchlist."""
    with get_session() as session:
        session.execute(sa_text(
            "UPDATE discovered_subreddits SET status='promoted', approved=1 WHERE subreddit=:sub"
        ), {"sub": subreddit})
        existing = session.execute(sa_text(
            "SELECT id FROM watchlist WHERE subreddit=:sub"
        ), {"sub": subreddit}).fetchone()
        if not existing:
            session.execute(sa_text(
                "INSERT INTO watchlist (subreddit, ticker, auto_discovered, active) "
                "VALUES (:sub, NULL, 1, 1)"
            ), {"sub": subreddit})
    return jsonify({"status": "approved", "subreddit": subreddit})


@app.route("/api/discoveries/<subreddit>/reject", methods=["POST"])
def reject_discovery(subreddit):
    """Reject a pending discovery."""
    with get_session() as session:
        session.execute(sa_text(
            "UPDATE discovered_subreddits SET status='rejected' WHERE subreddit=:sub"
        ), {"sub": subreddit})
    return jsonify({"status": "rejected", "subreddit": subreddit})


@app.route("/api/watchlist")
def api_watchlist():
    """Return all watchlist entries."""
    with get_session() as session:
        rows = session.execute(sa_text(
            "SELECT subreddit, ticker, auto_discovered, active, added_at "
            "FROM watchlist ORDER BY added_at DESC"
        )).fetchall()
    return jsonify([{
        "subreddit": r[0], "ticker": r[1],
        "auto_discovered": bool(r[2]), "active": bool(r[3]), "added_at": str(r[4])
    } for r in rows])


@app.route("/api/watchlist/<subreddit>/deactivate", methods=["POST"])
def deactivate_watchlist(subreddit):
    """Deactivate a watchlist entry (stop scraping it)."""
    with get_session() as session:
        session.execute(sa_text(
            "UPDATE watchlist SET active=0 WHERE subreddit=:sub"
        ), {"sub": subreddit})
    return jsonify({"status": "deactivated", "subreddit": subreddit})


@app.route("/api/discovered")
def api_discovered():
    """Return all discovered subreddits as JSON (backward compat)."""
    with get_session() as session:
        from database import DiscoveredSubreddit
        rows = session.query(DiscoveredSubreddit).order_by(
            DiscoveredSubreddit.members.desc()
        ).all()
        discovered = [
            {
                "subreddit": d.subreddit,
                "ticker": d.ticker,
                "members": d.members,
                "source": d.source,
                "approved": bool(d.approved),
                "status": d.status,
            }
            for d in rows
        ]
    return jsonify(discovered)


@app.route("/api/discover_now", methods=["POST"])
def api_discover_now():
    """Manually trigger discovery cycle (returns status)."""
    try:
        run_discovery_cycle()
        return jsonify({"status": "ok", "message": "Discovery cycle completed"})
    except Exception as e:
        logger.error("Manual discovery failed: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/price/<ticker>")
def api_price(ticker):
    """Fetch current price via yfinance. Gracefully returns null on failure."""
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        info = stock.fast_info

        price = getattr(info, "last_price", None)
        prev_close = getattr(info, "previous_close", None)

        if price is None or prev_close is None:
            slow_info = stock.info
            if price is None:
                price = slow_info.get("currentPrice") or slow_info.get("regularMarketPrice")
            if prev_close is None:
                prev_close = slow_info.get("previousClose")

        change_pct = None
        if price and prev_close and prev_close > 0:
            change_pct = round((price - prev_close) / prev_close * 100, 2)

        return jsonify({
            "ticker": ticker,
            "price": round(price, 2) if price else None,
            "previous_close": round(prev_close, 2) if prev_close else None,
            "change_pct": change_pct,
        })
    except Exception as e:
        logger.warning("yfinance failed for %s: %s", ticker, e)
        return jsonify({"ticker": ticker, "price": None, "previous_close": None, "change_pct": None})


# Background thread reference for the seed job
_seed_thread = None


@app.route("/admin/seed")
def admin_seed():
    """Trigger the one-time S&P 500 ticker probe. Protect with token query param."""
    if request.args.get("token") != ADMIN_SEED_TOKEN:
        return jsonify({"error": "unauthorized"}), 403
    global _seed_thread
    if _seed_thread and _seed_thread.is_alive():
        return jsonify({"status": "already_running"})
    _seed_thread = threading.Thread(target=discover_from_tickers, daemon=True)
    _seed_thread.start()
    return jsonify({"status": "started", "message": "Ticker probe running in background. Takes 2-4 hours."})


@app.route("/admin/seed/stop")
def admin_seed_stop():
    """Stop the running ticker seed job."""
    if request.args.get("token") != ADMIN_SEED_TOKEN:
        return jsonify({"error": "unauthorized"}), 403
    stop_seed_job()
    return jsonify({"status": "stop_requested"})


if __name__ == "__main__":
    logger.info("Initializing database...")
    init_db()

    logger.info("Running initial scrape...")
    try:
        scrape_all()
    except Exception as e:
        logger.error("Initial scrape failed: %s", e)

    try:
        check_and_record_alerts()
    except Exception as e:
        logger.error("Initial alert check failed: %s", e)

    logger.info("Running initial discovery cycle...")
    try:
        run_discovery_cycle()
    except Exception as e:
        logger.error("Initial discovery failed: %s", e)

    logger.info("Starting scheduler...")
    scheduler = create_scheduler()
    scheduler.start()

    logger.info("Starting Flask on port %d...", FLASK_PORT)
    try:
        app.run(host="0.0.0.0", port=FLASK_PORT, debug=FLASK_DEBUG)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
        scheduler.shutdown()
