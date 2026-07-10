from __future__ import annotations

import json
import re
from typing import Protocol

from openai import OpenAI

from .schemas import ExtractedClaim, ExtractedClaims, SubmissionData


CASHTAG = re.compile(r"\$([A-Z]{1,5}(?:\.[A-Z])?)\b")
PAREN_TICKER = re.compile(r"\(([A-Z]{1,5}(?:\.[A-Z])?)\)")
BULLISH = re.compile(r"\b(buy|bull(?:ish)?|long|undervalued|upside|calls?)\b", re.I)
BEARISH = re.compile(r"\b(sell|bear(?:ish)?|short|overvalued|downside|puts?)\b", re.I)
DD_TERMS = re.compile(
    r"\b(thesis|valuation|revenue|earnings|cash flow|catalyst|risk|margin|market cap|due diligence|dd)\b",
    re.I,
)
COMMON_WORDS = {"A", "AI", "CEO", "CFO", "DD", "EPS", "ETF", "IMO", "IPO", "SEC", "USA"}


def is_dd_candidate(submission: SubmissionData, min_chars: int = 500) -> bool:
    text = f"{submission.title}\n{submission.body}"
    flair_dd = bool(submission.flair and "dd" in submission.flair.lower())
    evidence_terms = len(set(term.lower() for term in DD_TERMS.findall(text)))
    return flair_dd or (len(submission.body) >= min_chars and evidence_terms >= 3)


class ClaimExtractor(Protocol):
    method: str

    def extract(self, submission: SubmissionData) -> list[ExtractedClaim]: ...


class RuleClaimExtractor:
    method = "rules"

    def __init__(self, default_horizon_days: int = 365) -> None:
        self.default_horizon_days = default_horizon_days

    def extract(self, submission: SubmissionData) -> list[ExtractedClaim]:
        text = f"{submission.title}\n{submission.body}"
        symbols = list(dict.fromkeys(CASHTAG.findall(text) + PAREN_TICKER.findall(text)))
        symbols = [symbol for symbol in symbols if symbol not in COMMON_WORDS]
        if not symbols:
            return []
        bull, bear = bool(BULLISH.search(text)), bool(BEARISH.search(text))
        if bull == bear:
            return []
        direction = "long" if bull else "short"
        confidence = 0.75 if CASHTAG.search(text) else 0.62
        return [
            ExtractedClaim(
                symbol=symbol,
                direction=direction,
                horizon_days=self.default_horizon_days,
                thesis=submission.title[:500],
                confidence=confidence,
            )
            for symbol in symbols[:3]
        ]


class OpenAIClaimExtractor:
    method = "openai"

    def __init__(self, api_key: str, model: str, default_horizon_days: int = 365) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.default_horizon_days = default_horizon_days

    def extract(self, submission: SubmissionData) -> list[ExtractedClaim]:
        schema = ExtractedClaims.model_json_schema()
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "Extract only explicit, actionable public-equity investment claims. "
                "Do not infer a position from a neutral mention. Use long or short. "
                "This system evaluates long-term investing theses. Use the author's stated "
                f"horizon; otherwise use {self.default_horizon_days} days. "
                "Ignore day trades and short-term setups. "
                "Return an empty claims list when ambiguous. Never provide investment advice."
            ),
            input=(
                f"Subreddit: {submission.subreddit}\nTitle: {submission.title}\n\n"
                f"Post body:\n{submission.body[:30000]}"
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "extracted_claims",
                    "strict": True,
                    "schema": schema,
                }
            },
        )
        return ExtractedClaims.model_validate(json.loads(response.output_text)).claims
