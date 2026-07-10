# Long-Term DD Track Record

A Dockerized research service that records timestamped Reddit stock theses, evaluates their
long-term performance against a benchmark, ranks authors with small-sample skepticism, and
monitors strong authors for new posts.

This is a research aid, not financial advice, a trading bot, or proof that an author will be
right again.

## What the MVP does

- Weekly: scans configured investing subreddits for substantial DD, discovers authors, and
  backfills the history that Reddit's official API makes available.
- Weekly (optional): searches manually seeded long-term winners and reports the earliest
  **API-accessible** matching DD and whether its author still appears active.
- Daily: checks tracked authors for new posts and evaluates claims whose long-term horizon has
  matured.
- Extracts ticker, long/short direction, horizon, and a short thesis. A conservative rules
  extractor is the default; optional OpenAI structured extraction can improve recall.
- Calculates asset return, SPY return, and directional excess return from adjusted prices.
- Produces an author score with a Beta(2,2) prior and separate evidence confidence. A small
  sample therefore stays near 50 and is visibly low-confidence.
- Exposes JSON endpoints and interactive API docs at `/docs`.

## Setup

Prerequisites: Docker Desktop and a Reddit account. No Codex plugin or skill is required.

1. Create a Reddit application at <https://www.reddit.com/prefs/apps>. Use a script or web app
   and read-only OAuth credentials. Do not put a Reddit password in this service.
2. Get an Alpha Vantage key at <https://www.alphavantage.co/support/#api-key>. The free tier is
   useful for a small proof of concept, but its current request allowance is too small for a
   broad production scan.
3. Copy `.env.example` to `.env` and fill in the Reddit and Alpha Vantage fields.
4. Optionally set `OPENAI_API_KEY`, choose an available model, and set
   `ENABLE_AI_EXTRACTION=true`. Leave it false until the rules baseline has been inspected.
5. Start the service:

   ```powershell
   docker compose up --build -d
   docker compose exec worker dd-tracker discover
   ```

6. Create an SSH tunnel with `ssh -L 8000:127.0.0.1:8000 mm`, then open
   <http://localhost:8000/> for the dashboard or <http://localhost:8000/configuration> to finish
   setup in the browser.

Useful commands:

```powershell
docker compose logs -f worker
docker compose exec worker dd-tracker discover
docker compose exec worker dd-tracker daily
docker compose exec worker dd-tracker evaluate
```

To reverse-scout known winners, set a deliberately chosen list such as
`WINNER_SYMBOLS=SYMBOL1,SYMBOL2`. Do not treat a winner-only sample as evidence the ranking model
works; validate on a point-in-time universe containing winners, laggards, delistings, and
bankruptcies.

## API

- `GET /health` — credential/config readiness (never returns secrets)
- `GET /` — frontend dashboard and operational controls
- `GET /configuration` — persistent configuration UI with masked credentials
- `GET /authors?tracked=true` — leaderboard and evidence strength
- `GET /authors/{username}` — posts, extracted claims, and outcomes
- `GET /claims?symbol=MSFT&evaluated=true` — claim ledger
- `GET /jobs` — scheduler audit log

## Scoring semantics

For a long claim:

`directional excess return = stock total return - SPY total return`

For a short claim the sign is reversed. A claim is a benchmark win when directional excess
return is positive. The author score combines a Bayesian-shrunk hit rate (80%) and a bounded
mean excess-return component (20%). `evidence_confidence` depends only on mature sample size;
it is not a prediction probability.

The entry is the first available adjusted daily close on or after the post date. That is
auditable and suitable for long horizons, but a later version should use exchange calendars
and next-session prices for posts published after market close.

## Important limitations

- Reddit prohibits unauthorized scraping. This service uses authenticated, read-only API
  access and intentionally has no HTML-scraping fallback. Review Reddit's current Developer and
  Data API terms before operating it, especially for commercial use.
- Reddit search/listings are capped and not a complete historical archive. “Earliest” here means
  earliest accessible result, never first-ever post.
- The MVP stores post text needed for extraction/audit. Reddit's terms can require deletion of
  cached content when access ends. Production needs a deletion/retention workflow and privacy
  policy before other users are served.
- Sending post text to any AI provider is a separate data-handling decision. AI is disabled by
  default. The service uses inference only; it does not train a model on Reddit content.
- Ticker/entity extraction can confuse companies, ETFs, renamed symbols, and cashtags. Add a
  point-in-time security master before trusting large backfills.
- Survivorship, selection, deletion, editing, repeated-call, and correlated-pick biases are
  substantial. Preserve first-seen snapshots and include delisted securities in serious tests.
- A one-year score takes a year to mature prospectively. Historical backfills accelerate product
  testing but weaken completeness guarantees.
- Alpha Vantage adjusted history availability and licensing depend on the account/plan. Cache
  each symbol series and move to a provider that explicitly covers delisted securities before
  production.

## Closest existing products

- [Chatter](https://www.producthunt.com/products/chatter-4) is the closest conceptual match: it
  presents Reddit posts and author performance histories.
- [ApeWisdom](https://apewisdom.io/) emphasizes ticker mentions and popularity.
- [Quiver Quantitative](https://www.quiverquant.com/splash/) provides WallStreetBets and broader
  alternative-data dashboards.
- [The Influencer Signal](https://finsig.ca/) tracks stock-picking voices across several media.

The defensible differentiation here is an open, inspectable claim ledger, long-term horizons,
benchmark-relative evaluation, honest uncertainty, and reverse discovery of early analysts.

## Next production milestones

1. Add Alembic migrations, per-provider rate limiting, price caching, and retry/backoff.
2. Add immutable post revisions and Reddit deletion/retention reconciliation.
3. Add a security master with symbol-history and delisting support.
4. Evaluate at fixed 1/3/5-year checkpoints plus the author's stated thesis horizon.
5. Measure extraction precision/recall on a hand-labelled set before enabling AI broadly.
6. Add thesis-quality dimensions that can be audited separately from returns: falsifiability,
   valuation basis, catalysts, risks, updates, and thesis closure.
7. Backtest rankings using strict as-of dates. Never let future outcomes influence which author
   would have been followed at an earlier date.
