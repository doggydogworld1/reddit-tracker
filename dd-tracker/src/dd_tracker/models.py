from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tracked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reputation_score: Mapped[float] = mapped_column(Float, default=50.0)
    evidence_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    mature_claims: Mapped[int] = mapped_column(Integer, default=0)
    benchmark_hit_rate: Mapped[float | None] = mapped_column(Float)
    mean_excess_return: Mapped[float | None] = mapped_column(Float)

    posts: Mapped[list[Post]] = relationship(back_populates="author")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (Index("ix_posts_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reddit_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"), index=True)
    subreddit: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    permalink: Mapped[str] = mapped_column(Text)
    flair: Mapped[str | None] = mapped_column(String(128))
    score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_dd_candidate: Mapped[bool] = mapped_column(Boolean, default=False)

    author: Mapped[Author] = relationship(back_populates="posts")
    claims: Mapped[list[Claim]] = relationship(back_populates="post", cascade="all, delete-orphan")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("post_id", "symbol", "direction", name="uq_post_claim"),
        Index("ix_claims_maturity", "evaluation_due_at", "evaluated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    thesis: Mapped[str] = mapped_column(Text, default="")
    extraction_method: Mapped[str] = mapped_column(String(16))
    extraction_confidence: Mapped[float] = mapped_column(Float)
    horizon_days: Mapped[int] = mapped_column(Integer, default=365)
    evaluation_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[float | None] = mapped_column(Float)
    benchmark_entry_price: Mapped[float | None] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float)
    benchmark_exit_price: Mapped[float | None] = mapped_column(Float)
    asset_return: Mapped[float | None] = mapped_column(Float)
    benchmark_return: Mapped[float | None] = mapped_column(Float)
    directional_excess_return: Mapped[float | None] = mapped_column(Float)
    beat_benchmark: Mapped[bool | None] = mapped_column(Boolean)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evaluation_error: Mapped[str | None] = mapped_column(Text)

    post: Mapped[Post] = relationship(back_populates="claims")


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")
    summary: Mapped[str] = mapped_column(Text, default="")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
