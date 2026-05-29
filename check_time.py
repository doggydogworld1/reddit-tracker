import sqlite3
c = sqlite3.connect("/app/data/reddit_tracker.db")
r = c.execute("SELECT subreddit, MIN(captured_at), MAX(captured_at) FROM snapshots GROUP BY subreddit LIMIT 5").fetchall()
for x in r:
    print(x)
print("---")
# Check if any snapshot is older than 24h
old = c.execute("SELECT COUNT(*) FROM snapshots WHERE captured_at < datetime('now', '-24 hours')").fetchone()[0]
recent = c.execute("SELECT COUNT(*) FROM snapshots WHERE captured_at >= datetime('now', '-24 hours')").fetchone()[0]
print(f"Older than 24h: {old}, Last 24h: {recent}")