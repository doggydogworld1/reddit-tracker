"""One-time cleanup: deactivate non-stock subreddits that were auto-promoted incorrectly."""
from database import init_db, get_session
from sqlalchemy import text

init_db()

BAD_SUBS = [
    "personalfinance", "PersonalFinanceCanada", "mutualfunds", "MonarchMoney",
    "FluentInFinance", "InvestmentClub", "phinvest", "ASX",
    "IndiaInvestments", "IndianStockMarket", "StockMarketIndia", "indiaStockMarket",
    "investing_discussion", "investingforbeginners", "dividendinvesting", "stocktwits",
]

with get_session() as session:
    for name in BAD_SUBS:
        result = session.execute(
            text("UPDATE watchlist SET active=0 WHERE subreddit=:s"), {"s": name}
        )
        print(f"Deactivated {name}: {result.rowcount} rows")

    count = session.execute(text("SELECT COUNT(*) FROM watchlist WHERE active=1")).scalar()
    print(f"Active subreddits after cleanup: {count}")