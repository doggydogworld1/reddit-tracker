from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from dd_tracker.api import app
from dd_tracker.database import get_session
from dd_tracker.models import Base


def test_dashboard_and_configuration_pages_render() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            dashboard = client.get("/")
            configuration = client.get("/configuration")
            stylesheet = client.get("/static/styles.css")
    finally:
        app.dependency_overrides.clear()

    assert dashboard.status_code == 200
    assert "Signal Ledger" in dashboard.text
    assert "Run discovery" in dashboard.text
    assert configuration.status_code == 200
    assert "Reddit access" in configuration.text
    assert stylesheet.status_code == 200

