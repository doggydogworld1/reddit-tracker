from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from statistics import fmean


@dataclass(frozen=True)
class ClaimOutcome:
    entry_price: float
    exit_price: float
    benchmark_entry_price: float
    benchmark_exit_price: float
    asset_return: float
    benchmark_return: float
    directional_excess_return: float
    beat_benchmark: bool


def first_price_on_or_after(prices: dict[date, float], target: date) -> float:
    candidates = [day for day in prices if day >= target]
    if not candidates:
        raise ValueError(f"No price on or after {target.isoformat()}")
    return prices[min(candidates)]


def evaluate_claim(
    asset_prices: dict[date, float],
    benchmark_prices: dict[date, float],
    entry_date: date,
    exit_date: date,
    direction: str,
) -> ClaimOutcome:
    entry = first_price_on_or_after(asset_prices, entry_date)
    exit_ = first_price_on_or_after(asset_prices, exit_date)
    benchmark_entry = first_price_on_or_after(benchmark_prices, entry_date)
    benchmark_exit = first_price_on_or_after(benchmark_prices, exit_date)
    asset_return = exit_ / entry - 1
    benchmark_return = benchmark_exit / benchmark_entry - 1
    sign = 1 if direction == "long" else -1
    directional_excess = sign * (asset_return - benchmark_return)
    return ClaimOutcome(
        entry_price=entry,
        exit_price=exit_,
        benchmark_entry_price=benchmark_entry,
        benchmark_exit_price=benchmark_exit,
        asset_return=asset_return,
        benchmark_return=benchmark_return,
        directional_excess_return=directional_excess,
        beat_benchmark=directional_excess > 0,
    )


@dataclass(frozen=True)
class AuthorScore:
    score: float
    evidence_confidence: float
    mature_claims: int
    benchmark_hit_rate: float | None
    mean_excess_return: float | None


def score_author(outcomes: list[tuple[bool, float]]) -> AuthorScore:
    n = len(outcomes)
    if not n:
        return AuthorScore(50.0, 0.0, 0, None, None)
    wins = sum(1 for won, _ in outcomes if won)
    raw_hit_rate = wins / n
    bayesian_hit_rate = (wins + 2) / (n + 4)  # Beta(2,2): skeptical small-sample prior.
    mean_excess = fmean(excess for _, excess in outcomes)
    magnitude_score = 50 + 50 * math.tanh(mean_excess / 0.20)
    evidence = 100 * (1 - math.exp(-n / 10))
    score = 0.80 * (100 * bayesian_hit_rate) + 0.20 * magnitude_score
    return AuthorScore(
        score=round(max(0.0, min(100.0, score)), 2),
        evidence_confidence=round(evidence, 2),
        mature_claims=n,
        benchmark_hit_rate=round(raw_hit_rate, 4),
        mean_excess_return=round(mean_excess, 6),
    )
