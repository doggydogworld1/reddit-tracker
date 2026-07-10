from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", enable_decoding=False)

    database_url: str = "sqlite:///./dd_tracker.db"
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "dd-track-record/0.1 (local development)"
    alpha_vantage_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    enable_ai_extraction: bool = False
    subreddits: list[str] = Field(
        default_factory=lambda: [
            "ValueInvesting",
            "stocks",
            "investing",
            "SecurityAnalysis",
            "DueDiligence",
        ]
    )
    benchmark_symbol: str = "SPY"
    discovery_post_limit: int = 200
    author_history_limit: int = 250
    min_post_chars: int = 500
    track_score_threshold: float = 55.0
    track_min_mature_claims: int = 3
    winner_symbols: list[str] = Field(default_factory=list)
    winner_search_limit: int = 250
    default_horizon_days: int = 365
    weekly_discovery_day: str = "sun"
    weekly_discovery_hour_utc: int = 10
    daily_monitor_hour_utc: int = 11

    @field_validator("subreddits", "winner_symbols", mode="before")
    @classmethod
    def parse_subreddits(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def reddit_configured(self) -> bool:
        return bool(self.reddit_client_id and self.reddit_client_secret)

    @property
    def market_data_configured(self) -> bool:
        return bool(self.alpha_vantage_api_key)

    @property
    def ai_configured(self) -> bool:
        return bool(self.enable_ai_extraction and self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
