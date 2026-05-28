"""SQLAlchemy models and database initialization."""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Index,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

from config import DATABASE_URL

logger = logging.getLogger(__name__)

Base = declarative_base()

engine = create_engine(DATABASE_URL, echo=False)
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)


class Snapshot(Base):
    """Stores a point-in-time snapshot of a subreddit's membership."""

    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subreddit = Column(String, nullable=False, index=True)
    ticker = Column(String, nullable=True)
    members = Column(Integer, nullable=False)
    active_users = Column(Integer, nullable=True)
    captured_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    __table_args__ = (
        Index("ix_snapshots_subreddit_captured", "subreddit", "captured_at"),
    )

    def __repr__(self):
        return (
            f"<Snapshot(subreddit={self.subreddit!r}, members={self.members}, "
            f"captured_at={self.captured_at})>"
        )


class Alert(Base):
    """Records a surge alert when a subreddit's velocity exceeds its baseline."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subreddit = Column(String, nullable=False)
    ticker = Column(String, nullable=True)
    velocity_pct = Column(Float, nullable=False)
    baseline_velocity_pct = Column(Float, nullable=False)
    multiplier = Column(Float, nullable=False)
    triggered_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return (
            f"<Alert(subreddit={self.subreddit!r}, velocity_pct={self.velocity_pct}, "
            f"multiplier={self.multiplier})>"
        )


@contextmanager
def get_session():
    """Return a context-manager session for database operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(engine)
    logger.info("Database initialized (tables created if missing)")