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
