from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    direction: Literal["long", "short"]
    horizon_days: int = Field(default=365, ge=90, le=3650)
    thesis: str = Field(default="", max_length=500)
    confidence: float = Field(ge=0, le=1)


class ExtractedClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ExtractedClaim]


class SubmissionData(BaseModel):
    reddit_id: str
    author: str
    subreddit: str
    title: str
    body: str
    permalink: str
    flair: str | None = None
    score: int = 0
    created_at: datetime


class ConfigurationUpdate(BaseModel):
    reddit_client_id: str = Field(default="", max_length=256)
    reddit_client_secret: str = Field(default="", max_length=512)
    reddit_user_agent: str = Field(default="", max_length=256)
    alpha_vantage_api_key: str = Field(default="", max_length=512)
    openai_api_key: str = Field(default="", max_length=512)
    openai_model: str = Field(default="gpt-5-mini", max_length=128)
    enable_ai_extraction: bool = False
    subreddits: str = Field(default="", max_length=2000)
    winner_symbols: str = Field(default="", max_length=2000)
    benchmark_symbol: str = Field(default="SPY", pattern=r"^[A-Za-z][A-Za-z0-9.\-]{0,14}$")
    default_horizon_days: int = Field(default=365, ge=90, le=3650)
    discovery_post_limit: int = Field(default=200, ge=10, le=1000)
    author_history_limit: int = Field(default=250, ge=10, le=1000)
    min_post_chars: int = Field(default=500, ge=100, le=20000)
    track_score_threshold: float = Field(default=55, ge=0, le=100)
    track_min_mature_claims: int = Field(default=3, ge=1, le=1000)
    winner_search_limit: int = Field(default=250, ge=10, le=1000)
    weekly_discovery_day: str = Field(
        default="sun", pattern=r"^(mon|tue|wed|thu|fri|sat|sun)$"
    )
    weekly_discovery_hour_utc: int = Field(default=10, ge=0, le=23)
    daily_monitor_hour_utc: int = Field(default=11, ge=0, le=23)
