"""One-time cleanup: deactivate non-stock subreddits that were auto-promoted incorrectly."""
from database import init_db, get_session
from sqlalchemy import text

init_db()

BAD_SUBS = [
    # Personal finance / general
    "personalfinance", "PersonalFinanceCanada", "mutualfunds", "MonarchMoney",
    "FluentInFinance", "InvestmentClub", "phinvest", "ASX",
    "IndiaInvestments", "IndianStockMarket", "StockMarketIndia", "indiaStockMarket",
    "investing_discussion", "investingforbeginners", "dividendinvesting", "stocktwits",
    # Games / not stocks
    "MonopolyGoTrading", "PokemonPocketTradeCo", "yokaiwatch",
    # Crypto
    "CryptoMarsShots",
    # Forex
    "FOREXTRADING", "Forex_Reddit",
    # Spam / low quality
    "XGramatikInsights", "WallStreetbetsELITE", "trakstocks",
    # Non-US markets (not useful for US retail investor thesis)
    "NepalStock", "KenyaStockMarket", "stock_trading_India", "OptionsTradingIndia",
    "IndianStreetBets", "ASX_Bets", "PennyStocksCanada", "Penny_Stocks_Canada",
    "UKpennystocks", "IndiaGrowthStocks",
    # Specific platforms (not stock communities)
    "trading212",
    # Too generic / not stock-specific
    "economy", "Economics", "portfolios", "Bogleheads",
]

with get_session() as session:
    for name in BAD_SUBS:
        result = session.execute(
            text("UPDATE watchlist SET active=0 WHERE subreddit=:s"), {"s": name}
        )
        print(f"Deactivated {name}: {result.rowcount} rows")

    count = session.execute(text("SELECT COUNT(*) FROM watchlist WHERE active=1")).scalar()
    print(f"Active subreddits after cleanup: {count}")