from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dd_tracker.config import Settings
from dd_tracker.extraction import RuleClaimExtractor
from dd_tracker.models import Base
from dd_tracker.schemas import SubmissionData
from dd_tracker.service import TrackerService


class FakeSocial:
    def search(self, subreddits: list[str], query: str, limit: int) -> list[SubmissionData]:
        return [
            SubmissionData(
                reddit_id="newer",
                author="later_author",
                subreddit="ValueInvesting",
                title=f"${query} long thesis",
                body="Valuation revenue margin cash flow catalyst risk undervalued. " * 20,
                permalink="https://reddit.com/newer",
                flair="DD",
                created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ),
            SubmissionData(
                reddit_id="older",
                author="early_author",
                subreddit="ValueInvesting",
                title=f"${query} long thesis",
                body="Valuation revenue margin cash flow catalyst risk undervalued. " * 20,
                permalink="https://reddit.com/older",
                flair="DD",
                created_at=datetime(2018, 1, 1, tzinfo=timezone.utc),
            ),
        ]

    def subreddit_new(self, subreddit: str, limit: int) -> list[SubmissionData]:
        return []

    def author_new(self, username: str, limit: int) -> list[SubmissionData]:
        return []


def test_winner_scout_labels_earliest_as_api_accessible() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite:///:memory:",
        winner_symbols=["ACME"],
        subreddits=["ValueInvesting"],
    )
    with Session(engine) as session:
        service = TrackerService(session, settings, FakeSocial(), None, RuleClaimExtractor())
        result = service.scout_winners()
    assert result["found"]["ACME"]["author"] == "early_author"
    assert result["found"]["ACME"]["qualification"] == "earliest API-accessible matching DD"

