from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from .configuration import configuration_view, load_settings, save_settings
from .database import get_session, init_db
from .jobs import run_daily, run_discovery, run_evaluation
from .models import Author, Claim, JobRun, Post
from .schemas import ConfigurationUpdate


PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


def percent(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def short_date(value: datetime | None) -> str:
    return "—" if value is None else value.strftime("%b %d, %Y")


templates.env.filters["percent"] = percent
templates.env.filters["short_date"] = short_date

app = FastAPI(
    title="Long-Term DD Track Record",
    version="0.2.0",
    description=(
        "Research aid that records timestamped Reddit stock theses and evaluates their "
        "long-term benchmark-relative outcomes. Not investment advice."
    ),
)
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    settings = load_settings(session)
    counts = {
        "authors": session.scalar(select(func.count()).select_from(Author)) or 0,
        "tracked": session.scalar(
            select(func.count()).select_from(Author).where(Author.tracked.is_(True))
        )
        or 0,
        "claims": session.scalar(select(func.count()).select_from(Claim)) or 0,
        "evaluated": session.scalar(
            select(func.count()).select_from(Claim).where(Claim.evaluated_at.is_not(None))
        )
        or 0,
    }
    leaders = session.scalars(
        select(Author).order_by(desc(Author.reputation_score)).limit(12)
    ).all()
    recent_claims = session.execute(
        select(Claim, Post, Author)
        .join(Post, Claim.post_id == Post.id)
        .join(Author, Post.author_id == Author.id)
        .order_by(desc(Post.created_at))
        .limit(12)
    ).all()
    recent_jobs = session.scalars(
        select(JobRun).order_by(desc(JobRun.started_at)).limit(6)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "counts": counts,
            "leaders": leaders,
            "recent_claims": recent_claims,
            "recent_jobs": recent_jobs,
            "configuration": configuration_view(settings),
            "page": "dashboard",
        },
    )


@app.get("/ui/authors/{username}", response_class=HTMLResponse)
def author_page(
    request: Request, username: str, session: Session = Depends(get_session)
) -> HTMLResponse:
    author = session.scalar(
        select(Author)
        .where(Author.username == username)
        .options(selectinload(Author.posts).selectinload(Post.claims))
    )
    if author is None:
        raise HTTPException(404, "Author not found")
    return templates.TemplateResponse(
        request=request,
        name="author.html",
        context={"author": author, "page": "authors"},
    )


@app.get("/configuration", response_class=HTMLResponse)
def configuration_page(
    request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="configuration.html",
        context={
            "configuration": configuration_view(load_settings(session)),
            "page": "configuration",
        },
    )


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    settings = load_settings(session)
    return {
        "status": "ok",
        "reddit_configured": settings.reddit_configured,
        "market_data_configured": settings.market_data_configured,
        "ai_extraction": settings.ai_configured,
    }


@app.get("/api/configuration")
def get_configuration(session: Session = Depends(get_session)) -> dict:
    return configuration_view(load_settings(session))


@app.put("/api/configuration")
def update_configuration(
    update: ConfigurationUpdate, session: Session = Depends(get_session)
) -> dict:
    return configuration_view(save_settings(session, update))


@app.post("/api/jobs/{job_name}", status_code=202)
def trigger_job(job_name: str, tasks: BackgroundTasks) -> dict:
    actions = {"discover": run_discovery, "daily": run_daily, "evaluate": run_evaluation}
    action = actions.get(job_name)
    if action is None:
        raise HTTPException(404, "Unknown job")
    tasks.add_task(action)
    return {"status": "queued", "job": job_name}


@app.get("/authors")
def authors(
    tracked: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[dict]:
    statement = select(Author).order_by(desc(Author.reputation_score)).limit(limit)
    if tracked is not None:
        statement = statement.where(Author.tracked == tracked)
    return [author_view(author) for author in session.scalars(statement).all()]


def author_view(author: Author) -> dict:
    return {
        "username": author.username,
        "tracked": author.tracked,
        "reputation_score": author.reputation_score,
        "evidence_confidence": author.evidence_confidence,
        "mature_claims": author.mature_claims,
        "benchmark_hit_rate": author.benchmark_hit_rate,
        "mean_excess_return": author.mean_excess_return,
        "last_scanned_at": author.last_scanned_at,
    }


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
        **author_view(author),
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
