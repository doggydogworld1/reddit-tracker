import sqlite3
c = sqlite3.connect("/app/data/reddit_tracker.db")
r = c.execute("SELECT subreddit, COUNT(*) as cnt FROM snapshots GROUP BY subreddit ORDER BY cnt DESC LIMIT 10").fetchall()
for x in r:
    print(x)
print("Total:", c.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])