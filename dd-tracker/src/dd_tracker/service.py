from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .extraction import ClaimExtractor, is_dd_candidate
from .models import Author, Claim, Post
from .providers import MarketDataProvider, SocialProvider
from .schemas import SubmissionData
from .scoring import evaluate_claim, score_author


def _mentions_symbol(item: SubmissionData, symbol: str) -> bool:
    import re

    text = f"{item.title}\n{item.body}"
    return bool(re.search(rf"(?<![A-Z])\$?{re.escape(symbol)}(?![A-Z])", text, re.I))


class TrackerService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        social: SocialProvider | None,
        market: MarketDataProvider | None,
        extractor: ClaimExtractor,
    ) -> None:
        self.session = session
        self.settings = settings
        self.social = social
        self.market = market
        self.extractor = extractor

    def ingest_submission(self, item: SubmissionData) -> tuple[Post, bool]:
        existing = self.session.scalar(select(Post).where(Post.reddit_id == item.reddit_id))
        if existing:
            return existing, False
        author = self.session.scalar(select(Author).where(Author.username == item.author))
        if author is None:
            author = Author(username=item.author)
            self.session.add(author)
            self.session.flush()
        candidate = is_dd_candidate(item, self.settings.min_post_chars)
        post = Post(
            reddit_id=item.reddit_id,
            author_id=author.id,
            subreddit=item.subreddit,
            title=item.title,
            body=item.body,
            permalink=item.permalink,
            flair=item.flair,
            score=item.score,
            created_at=item.created_at,
            is_dd_candidate=candidate,
        )
        self.session.add(post)
        self.session.flush()
        if candidate:
            for extracted in self.extractor.extract(item):
                self.session.add(
                    Claim(
                        post_id=post.id,
                        symbol=extracted.symbol.upper(),
                        direction=extracted.direction,
                        thesis=extracted.thesis,
                        extraction_method=self.extractor.method,
                        extraction_confidence=extracted.confidence,
                        horizon_days=extracted.horizon_days,
                        evaluation_due_at=item.created_at + timedelta(days=extracted.horizon_days),
                    )
                )
        self.session.commit()
        return post, True

    def discover(self) -> dict[str, int]:
        if self.social is None:
            raise RuntimeError("Reddit is not configured")
        new_posts = new_authors = history_posts = 0
        known_authors = {row[0] for row in self.session.execute(select(Author.username)).all()}
        discovered: set[str] = set()
        for subreddit in self.settings.subreddits:
            for item in self.social.subreddit_new(subreddit, self.settings.discovery_post_limit):
                if is_dd_candidate(item, self.settings.min_post_chars):
                    discovered.add(item.author)
                _, created = self.ingest_submission(item)
                new_posts += int(created)
        for username in sorted(discovered):
            if username not in known_authors:
                new_authors += 1
                for item in self.social.author_new(username, self.settings.author_history_limit):
                    _, created = self.ingest_submission(item)
                    history_posts += int(created)
        return {"new_posts": new_posts, "new_authors": new_authors, "history_posts": history_posts}

    def scout_winners(self) -> dict[str, object]:
        """Find earliest API-accessible DD for manually selected long-term winners."""
        if self.social is None:
            raise RuntimeError("Reddit is not configured")
        found: dict[str, dict[str, object]] = {}
        ingested = 0
        for symbol in self.settings.winner_symbols:
            candidates = [
                item
                for item in self.social.search(
                    self.settings.subreddits, symbol, self.settings.winner_search_limit
                )
                if _mentions_symbol(item, symbol)
                and is_dd_candidate(item, self.settings.min_post_chars)
            ]
            for item in candidates:
                _, created = self.ingest_submission(item)
                ingested += int(created)
            if candidates:
                earliest = min(candidates, key=lambda item: item.created_at)
                found[symbol] = {
                    "author": earliest.author,
                    "created_at": earliest.created_at.isoformat(),
                    "permalink": earliest.permalink,
                    "qualification": "earliest API-accessible matching DD",
                }
        return {
            "symbols_searched": len(self.settings.winner_symbols),
            "ingested": ingested,
            "found": found,
        }

    def monitor_tracked(self) -> dict[str, int]:
        if self.social is None:
            raise RuntimeError("Reddit is not configured")
        authors = self.session.scalars(select(Author).where(Author.tracked.is_(True))).all()
        new_posts = 0
        for author in authors:
            for item in self.social.author_new(author.username, 50):
                _, created = self.ingest_submission(item)
                new_posts += int(created)
            author.last_scanned_at = datetime.now(timezone.utc)
        self.session.commit()
        return {"tracked_authors": len(authors), "new_posts": new_posts}

    def evaluate_due(self, now: datetime | None = None) -> dict[str, int]:
        if self.market is None:
            raise RuntimeError("Market data is not configured")
        now = now or datetime.now(timezone.utc)
        due = self.session.scalars(
            select(Claim).where(Claim.evaluation_due_at <= now, Claim.evaluated_at.is_(None))
        ).all()
        benchmark_prices = self.market.daily_prices(self.settings.benchmark_symbol)
        evaluated = failed = 0
        for claim in due:
            try:
                asset_prices = self.market.daily_prices(claim.symbol)
                outcome = evaluate_claim(
                    asset_prices,
                    benchmark_prices,
                    claim.post.created_at.date(),
                    claim.evaluation_due_at.date(),
                    claim.direction,
                )
                for field, value in outcome.__dict__.items():
                    setattr(claim, field, value)
                claim.evaluated_at = now
                claim.evaluation_error = None
                evaluated += 1
            except Exception as exc:  # Persist provider/symbol errors without killing the batch.
                claim.evaluation_error = str(exc)[:1000]
                failed += 1
        self.session.commit()
        self.refresh_author_scores()
        return {"due": len(due), "evaluated": evaluated, "failed": failed}

    def refresh_author_scores(self) -> None:
        authors = self.session.scalars(select(Author)).all()
        for author in authors:
            rows = self.session.execute(
                select(Claim.beat_benchmark, Claim.directional_excess_return)
                .join(Post)
                .where(Post.author_id == author.id, Claim.evaluated_at.is_not(None))
            ).all()
            score = score_author([(bool(win), float(excess)) for win, excess in rows])
            author.reputation_score = score.score
            author.evidence_confidence = score.evidence_confidence
            author.mature_claims = score.mature_claims
            author.benchmark_hit_rate = score.benchmark_hit_rate
            author.mean_excess_return = score.mean_excess_return
            author.tracked = bool(
                score.mature_claims >= self.settings.track_min_mature_claims
                and score.score >= self.settings.track_score_threshold
            )
        self.session.commit()
