from datetime import date

import pytest

from dd_tracker.scoring import evaluate_claim, score_author


def test_long_claim_is_scored_relative_to_benchmark() -> None:
    dates = [date(2020, 1, 2), date(2021, 1, 4)]
    outcome = evaluate_claim(
        dict(zip(dates, [100.0, 150.0], strict=True)),
        dict(zip(dates, [100.0, 120.0], strict=True)),
        dates[0],
        date(2021, 1, 2),
        "long",
    )
    assert outcome.asset_return == pytest.approx(0.5)
    assert outcome.directional_excess_return == pytest.approx(0.3)
    assert outcome.beat_benchmark is True


def test_short_direction_reverses_relative_result() -> None:
    dates = [date(2020, 1, 2), date(2021, 1, 4)]
    outcome = evaluate_claim(
        dict(zip(dates, [100.0, 80.0], strict=True)),
        dict(zip(dates, [100.0, 110.0], strict=True)),
        dates[0],
        date(2021, 1, 2),
        "short",
    )
    assert outcome.directional_excess_return == pytest.approx(0.3)
    assert outcome.beat_benchmark is True


def test_one_lucky_pick_stays_low_evidence() -> None:
    score = score_author([(True, 1.0)])
    assert score.score < 70
    assert score.evidence_confidence < 10
    assert score.mature_claims == 1


def test_empty_author_is_neutral() -> None:
    score = score_author([])
    assert score.score == 50
    assert score.evidence_confidence == 0

