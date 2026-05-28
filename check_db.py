"""Quick DB check script."""
from database import init_db, get_session
from sqlalchemy import text

init_db()
with get_session() as session:
    active = session.execute(text("SELECT COUNT(*) FROM watchlist WHERE active=1")).scalar()
    total = session.execute(text("SELECT COUNT(*) FROM watchlist")).scalar()
    print(f"Active: {active}, Total: {total}")
    # Show auto-discovered active subs
    rows = session.execute(text("SELECT subreddit, ticker FROM watchlist WHERE active=1 AND auto_discovered=1")).fetchall()
    print(f"Auto-discovered active: {len(rows)}")
    for r in rows:
        print(f"  r/{r[0]} ({r[1]})")