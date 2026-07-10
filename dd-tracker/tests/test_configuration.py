from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dd_tracker.configuration import configuration_view, load_settings, save_settings
from dd_tracker.models import AppSetting, Base
from dd_tracker.schemas import ConfigurationUpdate


def test_configuration_persists_and_blank_secret_preserves_existing_value() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = ConfigurationUpdate(
            reddit_client_id="client-id",
            reddit_client_secret="super-secret",
            reddit_user_agent="tracker by u/tester",
            alpha_vantage_api_key="market-key",
            subreddits="ValueInvesting,stocks",
            winner_symbols="NVDA,COST",
            default_horizon_days=730,
        )
        save_settings(session, first)
        save_settings(
            session,
            ConfigurationUpdate(
                reddit_client_id="client-id",
                reddit_client_secret="",
                reddit_user_agent="tracker by u/tester",
                alpha_vantage_api_key="",
            ),
        )
        settings = load_settings(session)
        secret_row = session.get(AppSetting, "reddit_client_secret")

    assert settings.reddit_client_secret == "super-secret"
    assert settings.alpha_vantage_api_key == "market-key"
    assert secret_row is not None and secret_row.is_secret is True
    view = configuration_view(settings)
    assert view["reddit_secret_set"] is True
    assert "reddit_client_secret" not in view

