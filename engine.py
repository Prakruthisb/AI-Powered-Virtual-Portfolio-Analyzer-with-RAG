"""
engine.py — shared data + calculation layer for the dashboard.
Every page imports from here so there's exactly one source of truth
for the portfolio, prices, and math (Phase 1 logic, reused).
"""

import yfinance as yf
import pandas as pd
import streamlit as st


# ---------------------------------------------------------------
# Your portfolio (edit this, or use the "Add holding" form on the
# Portfolio page once the app is running).
# ---------------------------------------------------------------
DEFAULT_PORTFOLIO = {
    "TCS.NS": {"investment": 30000, "buy_price": 3000},
    "INFY.NS": {"investment": 25000, "buy_price": 1500},
    "RELIANCE.NS": {"investment": 25000, "buy_price": 2500},
    "HDFCBANK.NS": {"investment": 20000, "buy_price": 1600},
}

DISPLAY_NAMES = {
    "TCS.NS": "TCS",
    "INFY.NS": "INFY",
    "RELIANCE.NS": "RELIANCE",
    "HDFCBANK.NS": "HDFC BANK",
}


def get_portfolio() -> dict:
    """Portfolio lives in session_state so the 'Add holding' form can edit it live."""
    if "portfolio_raw" not in st.session_state:
        st.session_state["portfolio_raw"] = dict(DEFAULT_PORTFOLIO)
    return st.session_state["portfolio_raw"]


def display_name(ticker: str) -> str:
    return DISPLAY_NAMES.get(ticker, ticker.replace(".NS", ""))


# ---------------------------------------------------------------
# STEP 1/2/3 (Phase 1 logic) — shares from investment + buy price
# ---------------------------------------------------------------
def build_portfolio(raw_portfolio: dict) -> dict:
    portfolio = {}
    for ticker, data in raw_portfolio.items():
        shares = data["investment"] / data["buy_price"]
        portfolio[ticker] = {**data, "shares": shares}
    return portfolio


# ---------------------------------------------------------------
# STEP 4 (Phase 1 logic) — live prices, value, profit, return %
# Cached for 60s so navigating between pages doesn't refetch every time.
# ---------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def evaluate_portfolio(raw_portfolio: dict) -> dict:
    portfolio = build_portfolio(raw_portfolio)
    results = {}
    total_investment = 0.0
    total_current_value = 0.0

    for ticker, data in portfolio.items():
        stock = yf.Ticker(ticker)
        try:
            price = stock.fast_info["last_price"]
        except Exception:
            price = stock.info.get("currentPrice", data["buy_price"])

        current_value = price * data["shares"]
        profit = current_value - data["investment"]
        return_pct = (profit / data["investment"]) * 100

        results[ticker] = {
            "investment": data["investment"],
            "buy_price": data["buy_price"],
            "shares": round(data["shares"], 4),
            "current_price": round(price, 2),
            "current_value": round(current_value, 2),
            "profit": round(profit, 2),
            "return_pct": round(return_pct, 2),
        }
        total_investment += data["investment"]
        total_current_value += current_value

    total_profit = total_current_value - total_investment
    total_return_pct = (total_profit / total_investment * 100) if total_investment else 0

    return {
        "holdings": results,
        "total_investment": round(total_investment, 2),
        "total_current_value": round(total_current_value, 2),
        "total_profit": round(total_profit, 2),
        "total_return_pct": round(total_return_pct, 2),
    }


# ---------------------------------------------------------------
# Portfolio Growth Chart — reconstruct historical portfolio value
# as sum(shares_i * price_i(t)) for every day in the period.
# ---------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_portfolio_history(raw_portfolio: dict, period: str = "6mo") -> pd.DataFrame:
    portfolio = build_portfolio(raw_portfolio)
    tickers = list(portfolio.keys())

    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)["Close"]
    if isinstance(data, pd.Series):  # single ticker edge case
        data = data.to_frame(tickers[0])

    value = pd.Series(0.0, index=data.index)
    for ticker in tickers:
        value += data[ticker].ffill() * portfolio[ticker]["shares"]

    return value.rename("Portfolio Value").reset_index()


# ---------------------------------------------------------------
# Individual Stock Performance — normalized (rebased to 100) so
# stocks at very different price levels are comparable on one chart.
# ---------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_normalized_prices(tickers: list, period: str = "6mo") -> pd.DataFrame:
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)["Close"]
    if isinstance(data, pd.Series):
        data = data.to_frame(tickers[0])
    normalized = data / data.iloc[0] * 100
    return normalized.reset_index()


# ---------------------------------------------------------------
# News — latest headlines per holding
# ---------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def get_news(ticker: str, limit: int = 5) -> list:
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        items = []
    return items[:limit]