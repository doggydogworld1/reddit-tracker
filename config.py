DATABASE_URL = "sqlite:///reddit_tracker.db"

SCRAPE_INTERVAL_HOURS = 4   # how often to collect snapshots

# Subreddit watchlist: key = subreddit name, value = ticker symbol or None
WATCHLIST = {
    "wallstreetbets":   None,
    "investing":        None,
    "stocks":           None,
    "options":          None,
    "SecurityAnalysis": None,
    "tsla":             "TSLA",
    "nvidiainvestors":  "NVDA",
    "applestock":       "AAPL",
    "AMD_Stock":        "AMD",
    "AMZN":             "AMZN",
    "microsoft":        "MSFT",
    "GME":              "GME",
    "Superstonk":       "GME",
    "Palantir":         "PLTR",
    "sofistock":        "SOFI",
}

# Alert threshold: flag any subreddit whose 24h velocity is N× its 30-day average
SURGE_MULTIPLIER = 3.0

FLASK_PORT = 5050
FLASK_DEBUG = False