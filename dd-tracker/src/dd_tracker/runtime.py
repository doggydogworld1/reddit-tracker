from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import Settings
from .extraction import OpenAIClaimExtractor, RuleClaimExtractor
from .models import JobRun
from .providers import AlphaVantageProvider, RedditProvider
from .service import TrackerService


def build_service(session: Session, settings: Settings) -> TrackerService:
    social = (
        RedditProvider(
            settings.reddit_client_id,
            settings.reddit_client_secret,
            settings.reddit_user_agent,
        )
        if settings.reddit_configured
        else None
    )
    market = (
        AlphaVantageProvider(settings.alpha_vantage_api_key)
        if settings.market_data_configured
        else None
    )
    extractor = (
        OpenAIClaimExtractor(
            settings.openai_api_key, settings.openai_model, settings.default_horizon_days
        )
        if settings.ai_configured
        else RuleClaimExtractor(settings.default_horizon_days)
    )
    return TrackerService(session, settings, social, market, extractor)


def record_job(session: Session, name: str, action: Callable[[], dict]) -> dict:
    run = JobRun(job_name=name)
    session.add(run)
    session.commit()
    try:
        result = action()
        run.status = "succeeded"
        run.summary = json.dumps(result, default=str)
        return result
    except Exception as exc:
        session.rollback()
        run = session.get(JobRun, run.id)
        run.status = "failed"
        run.summary = str(exc)[:4000]
        raise
    finally:
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
