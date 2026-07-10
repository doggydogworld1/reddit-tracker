from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol

import httpx
import praw

from .schemas import SubmissionData


class SocialProvider(Protocol):
    def subreddit_new(self, subreddit: str, limit: int) -> list[SubmissionData]: ...

    def author_new(self, username: str, limit: int) -> list[SubmissionData]: ...

    def search(self, subreddits: list[str], query: str, limit: int) -> list[SubmissionData]: ...


class RedditProvider:
    def __init__(self, client_id: str, client_secret: str, user_agent: str) -> None:
        self.client = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            check_for_async=False,
        )
        self.client.read_only = True

    @staticmethod
    def _convert(item: object) -> SubmissionData | None:
        author = getattr(item, "author", None)
        if author is None:
            return None
        return SubmissionData(
            reddit_id=item.id,
            author=str(author),
            subreddit=str(item.subreddit),
            title=item.title or "",
            body=item.selftext or "",
            permalink=f"https://www.reddit.com{item.permalink}",
            flair=item.link_flair_text,
            score=item.score,
            created_at=datetime.fromtimestamp(item.created_utc, tz=timezone.utc),
        )

    def subreddit_new(self, subreddit: str, limit: int) -> list[SubmissionData]:
        return [
            converted
            for item in self.client.subreddit(subreddit).new(limit=limit)
            if (converted := self._convert(item)) is not None
        ]

    def author_new(self, username: str, limit: int) -> list[SubmissionData]:
        return [
            converted
            for item in self.client.redditor(username).submissions.new(limit=limit)
            if (converted := self._convert(item)) is not None
        ]

    def search(self, subreddits: list[str], query: str, limit: int) -> list[SubmissionData]:
        combined = "+".join(subreddits)
        return [
            converted
            for item in self.client.subreddit(combined).search(
                query, sort="new", time_filter="all", limit=limit
            )
            if (converted := self._convert(item)) is not None
        ]


class MarketDataProvider(Protocol):
    def daily_prices(self, symbol: str) -> dict[date, float]: ...


class AlphaVantageProvider:
    endpoint = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def daily_prices(self, symbol: str) -> dict[date, float]:
        response = httpx.get(
            self.endpoint,
            params={
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": symbol,
                "outputsize": "full",
                "apikey": self.api_key,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        series = payload.get("Time Series (Daily)")
        if not series:
            message = payload.get("Note") or payload.get("Information") or payload.get("Error Message")
            raise RuntimeError(message or f"No daily prices returned for {symbol}")
        return {
            date.fromisoformat(day): float(values.get("5. adjusted close", values["4. close"]))
            for day, values in series.items()
        }
