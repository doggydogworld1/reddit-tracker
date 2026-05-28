"""SQLAlchemy models and database initialization."""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Index,
    text,
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


class DiscoveredSubreddit(Base):
    """Tracks subreddits found via auto-discovery that aren't in the static watchlist."""

    __tablename__ = "discovered_subreddits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subreddit = Column(String, nullable=False, unique=True, index=True)
    ticker = Column(String, nullable=True)
    members = Column(Integer, nullable=True)
    source = Column(String, nullable=True)  # which seed found it (backward compat)
    discovered_via = Column(String, nullable=True)  # ticker_probe, search, related, sidebar
    ticker_guess = Column(String, nullable=True)
    description = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, promoted, rejected
    discovered_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    approved = Column(Integer, default=0)  # 1 = promoted, 0 = pending (backward compat)

    def __repr__(self):
        return (
            f"<DiscoveredSubreddit(subreddit={self.subreddit!r}, "
            f"members={self.members}, status={self.status})>"
        )


class Watchlist(Base):
    """Active watchlist stored in DB — replaces hardcoded config.WATCHLIST dict."""

    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subreddit = Column(String, unique=True, nullable=False, index=True)
    ticker = Column(String, nullable=True)
    auto_discovered = Column(Boolean, default=False)
    active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Watchlist(subreddit={self.subreddit!r}, ticker={self.ticker}, active={self.active})>"


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


def seed_watchlist_from_config():
    """One-time migration: if Watchlist table is empty, populate from config.WATCHLIST dict."""
    from config import WATCHLIST
    with get_session() as session:
        if session.query(Watchlist).count() == 0:
            for subreddit, ticker in WATCHLIST.items():
                session.add(Watchlist(subreddit=subreddit, ticker=ticker, auto_discovered=False, active=True))
            logger.info("Seeded watchlist with %d entries from config", len(WATCHLIST))


def migrate_discovered_subreddits():
    """Add new columns to discovered_subreddits if they don't exist yet (SQLite compat)."""
    with engine.connect() as conn:
        existing = [row[1] for row in conn.execute(text("PRAGMA table_info(discovered_subreddits)")).fetchall()]
        if "status" not in existing:
            conn.execute(text("ALTER TABLE discovered_subreddits ADD COLUMN status TEXT DEFAULT 'pending'"))
        if "discovered_via" not in existing:
            conn.execute(text("ALTER TABLE discovered_subreddits ADD COLUMN discovered_via TEXT"))
        if "ticker_guess" not in existing:
            conn.execute(text("ALTER TABLE discovered_subreddits ADD COLUMN ticker_guess TEXT"))
        if "description" not in existing:
            conn.execute(text("ALTER TABLE discovered_subreddits ADD COLUMN description TEXT"))
        if "is_single_ticker" not in existing:
            conn.execute(text("ALTER TABLE discovered_subreddits ADD COLUMN is_single_ticker BOOLEAN DEFAULT 0"))
        conn.commit()
    # Backfill: set status based on existing 'approved' column
    with engine.connect() as conn:
        conn.execute(text("UPDATE discovered_subreddits SET status='promoted' WHERE approved=1 AND status IS NULL"))
        conn.execute(text("UPDATE discovered_subreddits SET status='pending' WHERE approved=0 AND status IS NULL"))
        # Backfill is_single_ticker based on ticker_guess presence
        conn.execute(text("UPDATE discovered_subreddits SET is_single_ticker=1 WHERE ticker_guess IS NOT NULL AND ticker_guess != ''"))
        conn.commit()
    logger.info("Discovered subreddits migration complete")


# ── One-time cleanup: deactivate general finance subs ─────────────────────────

GENERAL_SUBS_TO_DEACTIVATE = [
    "wallstreetbets", "investing", "stocks", "options", "SecurityAnalysis",
    "SPACs", "pennystocks", "StockMarket", "Daytrading", "dividends",
    "ValueInvesting", "algotrading", "RobinHood", "weedstocks", "BBBY",
    "finance", "stockmarket", "personalfinance",
]


def deactivate_general_subs():
    """One-time cleanup: mark known general finance subs as inactive in watchlist."""
    with get_session() as session:
        deactivated = 0
        for sub in GENERAL_SUBS_TO_DEACTIVATE:
            result = session.execute(text(
                "UPDATE watchlist SET active=0 WHERE LOWER(subreddit)=LOWER(:sub)"
            ), {"sub": sub})
            deactivated += result.rowcount
        session.commit()
        if deactivated:
            logger.info("Deactivated %d general finance subreddit entries from watchlist", deactivated)


def init_db():
    """Create all tables if they don't exist, then run migrations and seed."""
    Base.metadata.create_all(engine)
    migrate_discovered_subreddits()
    seed_watchlist_from_config()
    deactivate_general_subs()
    logger.info("Database initialized (tables created if missing)")
