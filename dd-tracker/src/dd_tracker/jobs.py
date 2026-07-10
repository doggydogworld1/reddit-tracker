from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import get_settings
from .database import SessionLocal, init_db
from .runtime import build_service, record_job


def run_discovery() -> dict:
    settings = get_settings()
    with SessionLocal() as session:
        service = build_service(session, settings)

        def action() -> dict:
            result: dict[str, object] = {"discovery": service.discover()}
            if settings.winner_symbols:
                result["winner_scout"] = service.scout_winners()
            return result

        return record_job(session, "weekly_discovery", action)


def run_daily() -> dict:
    settings = get_settings()
    with SessionLocal() as session:
        service = build_service(session, settings)

        def action() -> dict:
            result: dict[str, object] = {"monitor": service.monitor_tracked()}
            if settings.market_data_configured:
                result["evaluation"] = service.evaluate_due()
            return result

        return record_job(session, "daily_monitor", action)


def run_evaluation() -> dict:
    settings = get_settings()
    with SessionLocal() as session:
        service = build_service(session, settings)
        return record_job(session, "evaluate_due", service.evaluate_due)


def worker() -> None:
    settings = get_settings()
    init_db()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_discovery,
        CronTrigger(
            day_of_week=settings.weekly_discovery_day,
            hour=settings.weekly_discovery_hour_utc,
            minute=0,
            timezone="UTC",
        ),
        id="weekly_discovery",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        run_daily,
        CronTrigger(hour=settings.daily_monitor_hour_utc, minute=0, timezone="UTC"),
        id="daily_monitor",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()

