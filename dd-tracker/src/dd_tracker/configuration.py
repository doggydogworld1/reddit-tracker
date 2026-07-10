from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import AppSetting
from .schemas import ConfigurationUpdate


SECRET_KEYS = {"reddit_client_secret", "alpha_vantage_api_key", "openai_api_key"}
EDITABLE_KEYS = set(ConfigurationUpdate.model_fields)


def load_settings(session: Session) -> Settings:
    base = get_settings()
    stored = {
        row.key: row.value
        for row in session.scalars(select(AppSetting)).all()
        if row.key in EDITABLE_KEYS
    }
    return Settings(**{**base.model_dump(), **stored})


def save_settings(session: Session, update: ConfigurationUpdate) -> Settings:
    values = update.model_dump()
    current = load_settings(session)
    proposed = {**current.model_dump(), **values}
    for key in SECRET_KEYS:
        if not values[key].strip():
            proposed[key] = getattr(current, key)
    validated = Settings(**proposed)

    for key in EDITABLE_KEYS:
        raw = values[key]
        if key in SECRET_KEYS and not str(raw).strip():
            continue
        if isinstance(raw, bool):
            serialized = "true" if raw else "false"
        else:
            serialized = str(raw).strip()
        row = session.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value=serialized, is_secret=key in SECRET_KEYS)
            session.add(row)
        else:
            row.value = serialized
            row.is_secret = key in SECRET_KEYS
    session.commit()
    return validated


def configuration_view(settings: Settings) -> dict[str, object]:
    return {
        "reddit_client_id": settings.reddit_client_id,
        "reddit_user_agent": settings.reddit_user_agent,
        "reddit_secret_set": bool(settings.reddit_client_secret),
        "alpha_vantage_key_set": bool(settings.alpha_vantage_api_key),
        "openai_key_set": bool(settings.openai_api_key),
        "openai_model": settings.openai_model,
        "enable_ai_extraction": settings.enable_ai_extraction,
        "subreddits": ",".join(settings.subreddits),
        "winner_symbols": ",".join(settings.winner_symbols),
        "benchmark_symbol": settings.benchmark_symbol,
        "default_horizon_days": settings.default_horizon_days,
        "discovery_post_limit": settings.discovery_post_limit,
        "author_history_limit": settings.author_history_limit,
        "min_post_chars": settings.min_post_chars,
        "track_score_threshold": settings.track_score_threshold,
        "track_min_mature_claims": settings.track_min_mature_claims,
        "winner_search_limit": settings.winner_search_limit,
        "weekly_discovery_day": settings.weekly_discovery_day,
        "weekly_discovery_hour_utc": settings.weekly_discovery_hour_utc,
        "daily_monitor_hour_utc": settings.daily_monitor_hour_utc,
        "reddit_configured": settings.reddit_configured,
        "market_data_configured": settings.market_data_configured,
        "ai_configured": settings.ai_configured,
    }
