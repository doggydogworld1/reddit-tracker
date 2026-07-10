from datetime import datetime, timezone

from dd_tracker.extraction import RuleClaimExtractor, is_dd_candidate
from dd_tracker.schemas import SubmissionData


def submission(title: str, body: str, flair: str | None = None) -> SubmissionData:
    return SubmissionData(
        reddit_id="abc123",
        author="careful_analyst",
        subreddit="ValueInvesting",
        title=title,
        body=body,
        permalink="https://reddit.com/example",
        flair=flair,
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )


def test_rule_extractor_finds_explicit_long_cashtag() -> None:
    item = submission(
        "$ACME is undervalued",
        "My long thesis covers valuation, revenue, cash flow, catalysts, and risks. " * 20,
        "DD",
    )
    claims = RuleClaimExtractor().extract(item)
    assert len(claims) == 1
    assert claims[0].symbol == "ACME"
    assert claims[0].direction == "long"
    assert claims[0].horizon_days == 365


def test_ambiguous_direction_produces_no_claim() -> None:
    item = submission("$ACME discussion", "The bull case and bear case are both worth reading.", "DD")
    assert RuleClaimExtractor().extract(item) == []


def test_substantial_fundamental_post_is_candidate() -> None:
    item = submission(
        "ACME analysis",
        "Revenue valuation margin cash flow catalyst risk. " * 20,
    )
    assert is_dd_candidate(item, min_chars=500)

