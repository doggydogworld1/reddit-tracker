from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import get_session, init_db
from .models import Author, Claim, JobRun, Post


app = FastAPI(
    title="Long-Term DD Track Record",
    version="0.1.0",
    description=(
        "Research aid that records timestamped Reddit stock theses and evaluates their "
        "long-term benchmark-relative outcomes. Not investment advice."
    ),
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "reddit_configured": settings.reddit_configured,
        "market_data_configured": settings.market_data_configured,
        "ai_extraction": settings.ai_configured,
    }


@app.get("/authors")
def authors(
    tracked: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[dict]:
    statement = select(Author).order_by(desc(Author.reputation_score)).limit(limit)
    if tracked is not None:
        statement = statement.where(Author.tracked == tracked)
    return [
        {
            "username": author.username,
            "tracked": author.tracked,
            "reputation_score": author.reputation_score,
            "evidence_confidence": author.evidence_confidence,
            "mature_claims": author.mature_claims,
            "benchmark_hit_rate": author.benchmark_hit_rate,
            "mean_excess_return": author.mean_excess_return,
            "last_scanned_at": author.last_scanned_at,
        }
        for author in session.scalars(statement).all()
    ]


@app.get("/authors/{username}")
def author_detail(username: str, session: Session = Depends(get_session)) -> dict:
    author = session.scalar(
        select(Author)
        .where(Author.username == username)
        .options(selectinload(Author.posts).selectinload(Post.claims))
    )
    if author is None:
        raise HTTPException(404, "Author not found")
    return {
        "username": author.username,
        "tracked": author.tracked,
        "reputation_score": author.reputation_score,
        "evidence_confidence": author.evidence_confidence,
        "mature_claims": author.mature_claims,
        "posts": [
            {
                "reddit_id": post.reddit_id,
                "title": post.title,
                "permalink": post.permalink,
                "created_at": post.created_at,
                "claims": [claim_view(claim) for claim in post.claims],
            }
            for post in sorted(author.posts, key=lambda row: row.created_at, reverse=True)
        ],
    }


def claim_view(claim: Claim) -> dict:
    return {
        "symbol": claim.symbol,
        "direction": claim.direction,
        "horizon_days": claim.horizon_days,
        "thesis": claim.thesis,
        "extraction_method": claim.extraction_method,
        "extraction_confidence": claim.extraction_confidence,
        "evaluation_due_at": claim.evaluation_due_at,
        "asset_return": claim.asset_return,
        "benchmark_return": claim.benchmark_return,
        "directional_excess_return": claim.directional_excess_return,
        "beat_benchmark": claim.beat_benchmark,
        "evaluated_at": claim.evaluated_at,
        "evaluation_error": claim.evaluation_error,
    }


@app.get("/claims")
def claims(
    symbol: str | None = None,
    evaluated: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[dict]:
    statement = select(Claim).order_by(desc(Claim.id)).limit(limit)
    if symbol:
        statement = statement.where(Claim.symbol == symbol.upper())
    if evaluated is True:
        statement = statement.where(Claim.evaluated_at.is_not(None))
    elif evaluated is False:
        statement = statement.where(Claim.evaluated_at.is_(None))
    return [claim_view(claim) for claim in session.scalars(statement).all()]


@app.get("/jobs")
def jobs(
    limit: int = Query(50, ge=1, le=200), session: Session = Depends(get_session)
) -> list[dict]:
    runs = session.scalars(select(JobRun).order_by(desc(JobRun.started_at)).limit(limit)).all()
    return [
        {
            "job_name": run.job_name,
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "summary": run.summary,
        }
        for run in runs
    ]

