import os

REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "REPLACE_ME")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "REPLACE_ME")
REDDIT_USER_AGENT    = "reddit_tracker/1.0 by YourUsername"

DATABASE_URL = "sqlite:///data/reddit_tracker.db"

SCRAPE_INTERVAL_HOURS = 4   # how often to collect snapshots

# Subreddit watchlist: key = subreddit name, value = ticker symbol or None
WATCHLIST = {
    "wallstreetbets":   None,
    "investing":        None,
    "stocks":           None,
    "options":          None,
    "SecurityAnalysis": None,
    "tsla":             "TSLA",
    "Nvidia":           "NVDA",       # replaced nvidiainvestors (private)
    "AAPL":             "AAPL",       # replaced applestock (404)
    "AMD_Stock":        "AMD",
    "AMZN":             "AMZN",
    "microsoft":        "MSFT",
    "GME":              "GME",
    "Superstonk":       "GME",
    "Palantir":         "PLTR",
    "sofistock":        "SOFI",
    # Additional stock subreddits
    "SPACs":            None,
    "pennystocks":      None,
    "StockMarket":      None,
    "Daytrading":       None,
    "dividends":        None,
    "ValueInvesting":   None,
    "algotrading":      None,
    "RobinHood":        None,
    "weedstocks":       None,
    "MVIS":             "MVIS",
    "SPY":              "SPY",
    "BBBY":             None,
    "MetaTrader":       "META",
    "teslainvestorsclub": "TSLA",
}

# Alert threshold: flag any subreddit whose 24h velocity is N× its 30-day average
SURGE_MULTIPLIER = 3.0

# Auto-discovery settings
DISCOVERY_ENABLED = True
DISCOVERY_INTERVAL_HOURS = 24  # how often to search for new subreddits
DISCOVERY_MAX_PER_RUN = 20      # max new subreddits to discover per cycle
DISCOVERY_MIN_SUBSCRIBERS = 500  # ignore tiny subreddits

# Seed subreddits to crawl for related communities
DISCOVERY_SEEDS = [
    "wallstreetbets",
    "investing",
    "stocks",
    "options",
    "pennystocks",
    "StockMarket",
]

ADMIN_SEED_TOKEN = "changeme123"   # Change before deploying — protects /admin/seed endpoint
SCRAPE_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; stock-tracker/1.0; personal project)"}

# Organic score: penalize velocity when stock already made a big price move
ORGANIC_SCORE = {
    "threshold_1d":  8.0,    # 1-day price move % where penalty = 0.5
    "threshold_7d":  15.0,   # 7-day price move % where penalty = 0.5
    "threshold_30d": 25.0,   # 30-day price move % where penalty = 0.5
    "k": 2.0,                # steepness — higher = harsher penalty curve
}

FLASK_PORT = 5050
FLASK_DEBUG = False
