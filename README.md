# Reddit Stock Community Velocity Tracker

Tracks membership growth velocity and acceleration across Reddit investment communities. The thesis: subreddits growing unusually fast are a leading indicator of retail investor interest in a stock.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run

```bash
python app.py
```

On first launch, the app will:
1. Initialize the SQLite database (`reddit_tracker.db`)
2. Run an immediate scrape of all watched subreddits
3. Start the APScheduler background job (every 4 hours by default)
4. Start the Flask web server on port 5050

### 3. Open the dashboard

Navigate to [http://localhost:5050](http://localhost:5050)

> **Note:** The leaderboard requires at least 2 scrape cycles to compute velocity. After the first run, you'll see member counts but velocity will show "—". Wait for the second scrape (or manually re-run) to see growth metrics.

## Adding subreddits

Edit the `WATCHLIST` dictionary in `config.py`:

```python
WATCHLIST = {
    "wallstreetbets":   None,     # no ticker association
    "tsla":             "TSLA",   # linked to ticker
    "your_subreddit":   "TICK",   # add your own
}
```

- **Key**: subreddit name (without the `r/` prefix)
- **Value**: stock ticker symbol, or `None` if the subreddit is general/investment-related

## Configuration

All settings live in `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `SCRAPE_INTERVAL_HOURS` | 4 | How often to collect snapshots |
| `SURGE_MULTIPLIER` | 3.0 | Alert threshold: flag subreddits whose 24h velocity exceeds N× their 30-day average |
| `FLASK_PORT` | 5050 | Web dashboard port |
| `FLASK_DEBUG` | False | Flask debug mode |

## Architecture

```
reddit_tracker/
├── config.py              # Settings and subreddit watchlist
├── database.py            # SQLAlchemy models (Snapshot, Alert) and DB init
├── scraper.py             # Requests-based scraper — fetches member counts via Reddit JSON API
├── analyzer.py            # Velocity, acceleration, leaderboard SQL queries
├── scheduler.py           # APScheduler job setup
├── app.py                 # Flask app + API routes
├── templates/
│   └── dashboard.html     # Single-page dashboard (Chart.js CDN)
├── requirements.txt
└── README.md
```

**Single-process design**: Everything runs in one Python process. APScheduler runs in a background thread; Flask runs in the main thread. SQLite stores all data locally.

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard HTML |
| `GET /api/leaderboard?limit=50` | Leaderboard data (JSON) |
| `GET /api/history/<subreddit>?days=30` | Membership history for sparklines |
| `GET /api/alerts` | Last 50 surge alerts |
| `GET /api/price/<ticker>` | Current stock price via yfinance |

## Tech stack

- **Python 3.11+**
- **Requests** — HTTP client for Reddit's public JSON endpoints
- **APScheduler** — in-process cron scheduler
- **SQLite via SQLAlchemy** — database (no external services)
- **Flask** — web server
- **yfinance** — optional price data overlay (gracefully skippable)
- **Chart.js** (CDN) — sparkline and detail charts