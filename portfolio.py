"""
Phase 1: Simple Portfolio Tracker (No Login, No Frontend)
-----------------------------------------------------------
Pure Python. Run it, it prints your portfolio's current value,
profit/loss, and % return. That's the whole scope for Phase 1.
"""

import yfinance as yf


# ---------------------------------------------------------------
# STEP 1: Fetch stock data
# ---------------------------------------------------------------
def get_stock_info(ticker: str) -> dict:
    """Fetch current price, company name, market cap, and volume for a ticker."""
    stock = yf.Ticker(ticker)
    info = stock.info

    # fast_info is quicker/more reliable for price than .info on some tickers
    try:
        current_price = stock.fast_info["last_price"]
    except Exception:
        current_price = info.get("currentPrice")

    return {
        "ticker": ticker,
        "company_name": info.get("longName", ticker),
        "current_price": current_price,
        "market_cap": info.get("marketCap"),
        "volume": info.get("volume"),
    }


def get_historical_prices(ticker: str, period: str = "1y"):
    """Return historical OHLCV data for a ticker."""
    stock = yf.Ticker(ticker)
    return stock.history(period=period)


# ---------------------------------------------------------------
# STEP 2 & 3: Portfolio logic — investments, buy price, shares
# ---------------------------------------------------------------
# Edit this to build your own portfolio.
# For each holding, give how much money (INR) you put in and the
# price you bought at. Shares are calculated automatically.
RAW_PORTFOLIO = {
    "TCS.NS": {"investment": 30000, "buy_price": 3000},
    "INFY.NS": {"investment": 25000, "buy_price": 1500},
    "RELIANCE.NS": {"investment": 25000, "buy_price": 2500},
    "HDFCBANK.NS": {"investment": 20000, "buy_price": 1600},
}


def build_portfolio(raw_portfolio: dict) -> dict:
    """Attach calculated share count to each holding."""
    portfolio = {}
    for ticker, data in raw_portfolio.items():
        shares = data["investment"] / data["buy_price"]
        portfolio[ticker] = {
            "investment": data["investment"],
            "buy_price": data["buy_price"],
            "shares": shares,
        }
    return portfolio


# ---------------------------------------------------------------
# STEP 4: Current value, profit/loss, % return
# ---------------------------------------------------------------
def evaluate_portfolio(portfolio: dict) -> dict:
    """Fetch current prices and compute value/profit/return per holding + totals."""
    results = {}
    total_investment = 0
    total_current_value = 0

    for ticker, data in portfolio.items():
        info = get_stock_info(ticker)
        current_price = info["current_price"]

        current_value = current_price * data["shares"]
        profit = current_value - data["investment"]
        return_pct = (profit / data["investment"]) * 100

        results[ticker] = {
            "company_name": info["company_name"],
            "investment": data["investment"],
            "buy_price": data["buy_price"],
            "shares": round(data["shares"], 4),
            "current_price": round(current_price, 2),
            "current_value": round(current_value, 2),
            "profit": round(profit, 2),
            "return_pct": round(return_pct, 2),
        }

        total_investment += data["investment"]
        total_current_value += current_value

    total_profit = total_current_value - total_investment
    total_return_pct = (total_profit / total_investment) * 100

    return {
        "holdings": results,
        "total_investment": round(total_investment, 2),
        "total_current_value": round(total_current_value, 2),
        "total_profit": round(total_profit, 2),
        "total_return_pct": round(total_return_pct, 2),
    }


# ---------------------------------------------------------------
# Pretty print — matches the "Phase 1 Result" format
# ---------------------------------------------------------------
def print_report(report: dict):
    print("=" * 45)
    print("PORTFOLIO REPORT".center(45))
    print("=" * 45)

    for ticker, h in report["holdings"].items():
        print(f"\n{h['company_name']} ({ticker})")
        print(f"  Investment:     ₹{h['investment']:,.0f}")
        print(f"  Current Value:  ₹{h['current_value']:,.0f}")
        sign = "+" if h["profit"] >= 0 else ""
        print(f"  Profit/Loss:    {sign}₹{h['profit']:,.0f}  ({sign}{h['return_pct']}%)")

    print("\n" + "-" * 45)
    print("TOTAL")
    print(f"  Initial Investment: ₹{report['total_investment']:,.0f}")
    print(f"  Current Value:      ₹{report['total_current_value']:,.0f}")
    sign = "+" if report["total_profit"] >= 0 else ""
    print(f"  Return:             {sign}{report['total_return_pct']}%")
    print("=" * 45)


if __name__ == "__main__":
    portfolio = build_portfolio(RAW_PORTFOLIO)
    report = evaluate_portfolio(portfolio)
    print_report(report)